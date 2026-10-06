from flask import Flask, request, send_file, render_template, jsonify
import os
import re
import base64
import zipfile
import zlib
from io import BytesIO
from PIL import Image
from werkzeug.exceptions import HTTPException

app = Flask(__name__)
# Reject oversized uploads before they reach the handlers
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024

# Constants for Go board
BOARD_SIZE = 19
LETTERS = 'abcdefghijklmnopqrs'  # SGF uses letters for coordinates
MAX_IMAGE_SIZE = (64, 64)  # Maximum dimensions for images
ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# Pillow refuses images over twice this many pixels, which stops small
# uploads that would expand into huge bitmaps in memory
Image.MAX_IMAGE_PIXELS = 16_000_000

# Payload type markers (first byte of the content)
TYPE_TEXT = b'T'
TYPE_IMAGE = b'I'

# First byte of every payload: whether the content after it is zlib-compressed
STORED_RAW = b'R'
STORED_ZLIB = b'Z'

# Each game holds one bit per stone, and every point on the board is used
BITS_PER_GAME = BOARD_SIZE * BOARD_SIZE
BYTES_PER_GAME = BITS_PER_GAME // 8

# Upper bounds that keep a crafted upload from exhausting memory
MAX_DECOMPRESSED_SIZE = 1024 * 1024
MAX_GAMES = 2000

# Game name carries the chunk position so files can be decoded in any order
GAME_NAME_RE = re.compile(r'GN\[hexago (\d+)/(\d+)\]')
MOVE_RE = re.compile(r';([BW])\[([a-s])([a-s])\]')


class DecodeError(ValueError):
    pass


def build_board_path():
    """Return every board point in a square spiral starting from the center."""
    x = y = BOARD_SIZE // 2
    path = [(x, y)]
    dx = [1, 0, -1, 0]  # Direction vectors
    dy = [0, 1, 0, -1]
    dir_idx = 0
    step = 1
    while len(path) < BITS_PER_GAME:
        for _ in range(2):
            for _ in range(step):
                x += dx[dir_idx]
                y += dy[dir_idx]
                if 0 <= x < BOARD_SIZE and 0 <= y < BOARD_SIZE:
                    path.append((x, y))
            dir_idx = (dir_idx + 1) % 4
        step += 1
    return path


BOARD_PATH = build_board_path()


def process_image(image_data):
    """Resize an image to fit the board budget and return it as compact WebP bytes."""
    try:
        img = Image.open(BytesIO(image_data))
        if img.mode in ('RGBA', 'LA') or 'transparency' in img.info:
            # Put transparent areas on white instead of whatever color they hide
            img = img.convert('RGBA')
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.getchannel('A'))
            img = background
        elif img.mode != 'RGB':
            img = img.convert('RGB')

        # Shrink only, while maintaining aspect ratio
        img.thumbnail(MAX_IMAGE_SIZE, Image.Resampling.LANCZOS)

        buffered = BytesIO()
        img.save(buffered, format='WEBP', quality=70)
        return buffered.getvalue()
    except Exception:
        raise ValueError('Could not read the image. Please upload a valid PNG, JPG or GIF.')


def bytes_to_binary(data):
    return ''.join(format(byte, '08b') for byte in data)


def binary_to_bytes(binary):
    usable = len(binary) - len(binary) % 8
    return bytes(int(binary[i:i+8], 2) for i in range(0, usable, 8))


def build_payload(type_marker, data):
    content = type_marker + data
    compressed = zlib.compress(content, 9)
    # zlib adds a few bytes of overhead, so short content is smaller left as is
    if len(compressed) < len(content):
        return STORED_ZLIB + compressed
    return STORED_RAW + content


def encode_chunk(chunk, index, total):
    """Encode one chunk of bytes as a single SGF game."""
    binary = bytes_to_binary(chunk)

    moves = []
    for bit, (x, y) in zip(binary, BOARD_PATH):
        # Black = 1, White = 0
        color = 'B' if bit == '1' else 'W'
        moves.append(f";{color}[{LETTERS[x]}{LETTERS[y]}]")

    header = f"(;GM[1]FF[4]SZ[{BOARD_SIZE}]CA[UTF-8]GN[hexago {index}/{total}]"
    return header + ''.join(moves) + ')'


def encode_payload(payload):
    chunks = [payload[i:i+BYTES_PER_GAME] for i in range(0, len(payload), BYTES_PER_GAME)]
    if len(chunks) > MAX_GAMES:
        raise ValueError('Content is too large to encode.')
    return [encode_chunk(chunk, i + 1, len(chunks)) for i, chunk in enumerate(chunks)]


def decode_sgf(sgf_content):
    """Return (index, total, chunk bytes) for one hexago SGF game."""
    match = GAME_NAME_RE.search(sgf_content)
    if not match:
        raise DecodeError('One of the files is not a Hexago game.')
    index, total = int(match.group(1)), int(match.group(2))

    binary = ''.join('1' if color == 'B' else '0' for color, _, _ in MOVE_RE.findall(sgf_content))
    return index, total, binary_to_bytes(binary)


def decode_games(sgf_contents):
    """Reassemble a payload from SGF games given in any order and unpack it."""
    chunks = {}
    totals = set()
    for content in sgf_contents:
        index, total, chunk = decode_sgf(content)
        if chunks.get(index, chunk) != chunk:
            raise DecodeError('The files come from different encodings.')
        totals.add(total)
        chunks[index] = chunk

    if len(totals) != 1:
        raise DecodeError('The files come from different encodings.')
    total = totals.pop()
    if total > MAX_GAMES:
        raise DecodeError('Too many games in this encoding.')
    missing = [i for i in range(1, total + 1) if i not in chunks]
    if missing:
        raise DecodeError(f'Missing {len(missing)} of {total} game files.')

    payload = b''.join(chunks[i] for i in range(1, total + 1))
    storage, body = payload[:1], payload[1:]
    if storage == STORED_RAW:
        if not body:
            raise DecodeError('The game files are corrupted.')
        return body[:1], body[1:]
    if storage != STORED_ZLIB:
        raise DecodeError('The game files are corrupted.')

    decompressor = zlib.decompressobj()
    try:
        data = decompressor.decompress(body, MAX_DECOMPRESSED_SIZE)
    except zlib.error:
        raise DecodeError('The game files are corrupted.')
    if decompressor.unconsumed_tail:
        raise DecodeError('Decoded content is too large.')
    if not decompressor.eof:
        raise DecodeError('The game files are corrupted.')
    return data[:1], data[1:]


def create_zip_file(sgf_contents):
    memory_file = BytesIO()
    width = len(str(len(sgf_contents)))
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for i, content in enumerate(sgf_contents):
            # Zero-padded names keep the files in order when sorted by name
            zf.writestr(f'game_{i+1:0{width}d}.sgf', content)
    memory_file.seek(0)
    return memory_file


@app.route('/')
def index():
    return render_template('index.html')


def payload_from_request():
    """Build the payload for a text or image encode request.

    Raises ValueError with a user-facing message when the request is unusable.
    """
    # Handle text message
    if request.is_json and 'message' in request.json:
        message = request.json['message']
        if not isinstance(message, str) or not message:
            raise ValueError('No message provided')
        return build_payload(TYPE_TEXT, message.encode('utf-8'))

    # Handle image upload
    if 'image' in request.files:
        image = request.files['image']
        if not image or not image.filename:
            raise ValueError('No image provided')

        if '.' not in image.filename or \
           image.filename.rsplit('.', 1)[1].lower() not in ALLOWED_IMAGE_EXTENSIONS:
            raise ValueError('Invalid image format. Allowed formats: PNG, JPG, JPEG, GIF')

        return build_payload(TYPE_IMAGE, process_image(image.read()))

    raise ValueError('No content provided')


def encode_request():
    """Return (payload, sgf_contents) for the current request, or an error response."""
    try:
        payload = payload_from_request()
        return payload, encode_payload(payload)
    except ValueError as e:
        return None, (jsonify({'error': str(e)}), 400)
    except HTTPException:
        # Oversized or malformed requests keep their own status codes
        raise
    except Exception:
        app.logger.exception('Encoding failed')
        return None, (jsonify({'error': 'Server error while encoding.'}), 500)


@app.route('/encode', methods=['POST'])
def encode():
    payload, result = encode_request()
    if payload is None:
        return result

    return send_file(
        create_zip_file(result),
        mimetype='application/zip',
        as_attachment=True,
        download_name='hexago_games.zip'
    )


@app.route('/preview', methods=['POST'])
def preview():
    """Encode without downloading, so the page can draw the boards."""
    payload, result = encode_request()
    if payload is None:
        return result

    return jsonify({
        'payload_bytes': len(payload),
        'bytes_per_game': BYTES_PER_GAME,
        'games': result,
    })


@app.route('/decode', methods=['POST'])
def decode():
    files = [f for f in request.files.getlist('file') if f.filename.lower().endswith('.sgf')]
    if not files:
        return jsonify({'error': 'No .sgf files uploaded'}), 400

    try:
        sgf_contents = []
        for file in files:
            try:
                sgf_contents.append(file.read().decode('utf-8'))
            except UnicodeDecodeError:
                raise DecodeError(f'{file.filename} is not a valid SGF file.')

        type_marker, data = decode_games(sgf_contents)

        if type_marker == TYPE_IMAGE:
            try:
                img = Image.open(BytesIO(data))
                buffered = BytesIO()
                img.save(buffered, format='PNG')
            except Exception:
                raise DecodeError('The hidden image is corrupted.')
            return jsonify({
                'type': 'image',
                'data': base64.b64encode(buffered.getvalue()).decode()
            })

        if type_marker == TYPE_TEXT:
            try:
                message = data.decode('utf-8')
            except UnicodeDecodeError:
                raise DecodeError('The hidden message is corrupted.')
            return jsonify({'type': 'text', 'message': message})

        raise DecodeError('Unknown content type.')
    except DecodeError as e:
        return jsonify({'error': str(e)}), 400
    except Exception:
        app.logger.exception('Decoding failed')
        return jsonify({'error': 'Server error while decoding.'}), 500


@app.errorhandler(413)
def too_large(_):
    return jsonify({'error': 'Upload is too large (5 MB max).'}), 413


@app.errorhandler(400)
def bad_request(_):
    return jsonify({'error': 'The request could not be understood.'}), 400


@app.route('/capacity')
def get_capacity():
    return jsonify({
        'max_moves_per_game': BITS_PER_GAME,
        'max_bytes_per_game': BYTES_PER_GAME,
    })


if __name__ == '__main__':
    # Debug mode exposes an interactive debugger, so it is opt-in only
    debug = os.environ.get('FLASK_DEBUG') == '1'
    app.run(debug=debug, port=5001)
