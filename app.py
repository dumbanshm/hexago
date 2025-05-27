from flask import Flask, request, send_file, render_template, jsonify
import os
import base64
import zipfile
from io import BytesIO
import tempfile
import random
import re
from PIL import Image
import numpy as np

app = Flask(__name__)

# Constants for Go board
BOARD_SIZE = 19
LETTERS = 'abcdefghijklmnopqrst'  # SGF uses letters for coordinates
MAX_IMAGE_SIZE = (64, 64)  # Maximum dimensions for images

def create_sgf_header():
    return "(;GM[1]FF[4]SZ[19]CA[UTF-8])"

def is_valid_move(board, x, y):
    if x < 0 or x >= BOARD_SIZE or y < 0 or y >= BOARD_SIZE:
        return False
    if board[y][x] != 0:  # Position already occupied
        return False
    return True

def process_image(image_data):
    """Process and resize image, convert to base64."""
    try:
        # Open image from bytes
        img = Image.open(BytesIO(image_data))
        
        # Convert to RGB if necessary
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Calculate new size while maintaining aspect ratio
        ratio = min(MAX_IMAGE_SIZE[0] / img.width, MAX_IMAGE_SIZE[1] / img.height)
        new_size = (int(img.width * ratio), int(img.height * ratio))
        img = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Convert to base64
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        img_str = base64.b64encode(buffered.getvalue()).decode()
        
        # Add metadata for reconstruction
        metadata = f"{img.width},{img.height}"
        return f"IMG:{metadata}:{img_str}"
    except Exception as e:
        raise ValueError(f"Error processing image: {str(e)}")

def reconstruct_image(encoded_data):
    """Reconstruct image from encoded data."""
    try:
        if not encoded_data.startswith("IMG:"):
            return None
            
        # Extract metadata and image data
        _, metadata, img_str = encoded_data.split(":", 2)
        width, height = map(int, metadata.split(","))
        
        # Decode base64 and create image
        img_data = base64.b64decode(img_str)
        img = Image.open(BytesIO(img_data))
        
        return img
    except Exception as e:
        raise ValueError(f"Error reconstructing image: {str(e)}")

def string_to_binary(text):
    # Convert string to UTF-8 bytes, then to binary string
    binary = ''.join(format(byte, '08b') for byte in text.encode('utf-8'))
    return binary

def binary_to_string(binary):
    # Pad binary string to be multiple of 8
    binary = binary + '0' * ((8 - len(binary) % 8) % 8)
    
    # Convert binary string back to bytes
    bytes_data = bytearray()
    for i in range(0, len(binary), 8):
        byte = binary[i:i+8]
        try:
            bytes_data.append(int(byte, 2))
        except ValueError:
            continue
    
    # Convert bytes back to UTF-8 string
    try:
        return bytes_data.decode('utf-8').rstrip('\x00')
    except UnicodeDecodeError:
        # Handle partial UTF-8 sequences by removing incomplete characters
        for i in range(len(bytes_data) - 1, -1, -1):
            try:
                return bytes_data[:i].decode('utf-8').rstrip('\x00')
            except UnicodeDecodeError:
                continue
        return ''

def encode_message(message):
    # Convert message to binary using UTF-8
    binary = string_to_binary(message)
    
    # Initialize empty board
    board = [[0] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    moves = []
    
    # Use binary data to generate moves
    x, y = BOARD_SIZE // 2, BOARD_SIZE // 2  # Start from center
    dx = [1, 0, -1, 0]  # Direction vectors
    dy = [0, 1, 0, -1]
    dir_idx = 0
    
    for bit in binary:
        # Find next valid move
        attempts = 0
        while attempts < 4:
            new_x = x + dx[dir_idx]
            new_y = y + dy[dir_idx]
            
            if is_valid_move(board, new_x, new_y):
                x, y = new_x, new_y
                break
                
            dir_idx = (dir_idx + 1) % 4
            attempts += 1
            
        if attempts == 4:
            # If no valid moves found, start a new game
            break
            
        # Add move to SGF
        board[y][x] = 1 if bit == '1' else 2
        color = 'B' if bit == '1' else 'W'
        moves.append(f";{color}[{LETTERS[x]}{LETTERS[y]}]")
    
    # Create SGF content
    sgf_content = create_sgf_header() + ''.join(moves) + ')'
    return sgf_content

def decode_sgf(sgf_content):
    # Extract moves from SGF content using regex
    moves = re.findall(r';([BW])\[([a-s])([a-s])\]', sgf_content)
    
    # Convert moves back to binary
    binary = ''
    for color, x, y in moves:
        # Black = 1, White = 0
        bit = '1' if color == 'B' else '0'
        binary += bit
    
    # Convert binary back to text using UTF-8
    return binary_to_string(binary)

def calculate_max_moves():
    # Initialize empty board
    board = [[0] * BOARD_SIZE for _ in range(BOARD_SIZE)]
    x, y = BOARD_SIZE // 2, BOARD_SIZE // 2  # Start from center
    dx = [1, 0, -1, 0]  # Direction vectors
    dy = [0, 1, 0, -1]
    dir_idx = 0
    moves = 0
    
    # Keep trying moves until we can't place any more
    while True:
        attempts = 0
        placed = False
        while attempts < 4:
            new_x = x + dx[dir_idx]
            new_y = y + dy[dir_idx]
            
            if is_valid_move(board, new_x, new_y):
                x, y = new_x, new_y
                board[y][x] = 1
                moves += 1
                placed = True
                break
                
            dir_idx = (dir_idx + 1) % 4
            attempts += 1
            
        if not placed:
            break
    
    return moves

def create_zip_file(sgf_contents):
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        for i, content in enumerate(sgf_contents):
            zf.writestr(f'game_{i+1}.sgf', content)
    memory_file.seek(0)
    return memory_file

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/encode', methods=['POST'])
def encode():
    try:
        # Handle text message
        if request.is_json and 'message' in request.json:
            message = request.json['message']
            if not message:
                return jsonify({'error': 'No message provided'}), 400
            
            # Calculate optimal chunk size based on UTF-8 encoding
            max_moves = calculate_max_moves()
            chunk_size = (max_moves // 8) // 4  # Account for UTF-8's max 4 bytes per char
            chunks = [message[i:i+chunk_size] for i in range(0, len(message), chunk_size)]
            
            # Create SGF files for each chunk
            sgf_contents = [encode_message(chunk) for chunk in chunks]
        
        # Handle image upload
        elif 'image' in request.files:
            image = request.files['image']
            if not image:
                return jsonify({'error': 'No image provided'}), 400
            
            # Check file extension
            allowed_extensions = {'png', 'jpg', 'jpeg', 'gif'}
            if '.' not in image.filename or \
               image.filename.rsplit('.', 1)[1].lower() not in allowed_extensions:
                return jsonify({'error': 'Invalid image format. Allowed formats: PNG, JPG, JPEG, GIF'}), 400
                
            try:
                # Process image and convert to encoded string
                img_data = process_image(image.read())
                
                # Split into chunks and encode
                max_moves = calculate_max_moves()
                chunk_size = (max_moves // 8)  # Each chunk can hold this many bytes
                chunks = [img_data[i:i+chunk_size] for i in range(0, len(img_data), chunk_size)]
                
                # Create SGF files for each chunk
                sgf_contents = [encode_message(chunk) for chunk in chunks]
            except ValueError as e:
                return jsonify({'error': str(e)}), 400
            except Exception as e:
                return jsonify({'error': f'Error processing image: {str(e)}'}), 500
        else:
            return jsonify({'error': 'No content provided'}), 400
        
        # Create zip file
        zip_buffer = create_zip_file(sgf_contents)
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name='hexago_games.zip'
        )
    except Exception as e:
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/decode', methods=['POST'])
def decode():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
        
    files = request.files.getlist('file')
    decoded_messages = []
    
    for file in files:
        if file.filename.endswith('.sgf'):
            sgf_content = file.read().decode('utf-8')
            decoded_text = decode_sgf(sgf_content)
            if decoded_text:  # Only add non-empty messages
                decoded_messages.append(decoded_text)
    
    if not decoded_messages:
        return jsonify({'error': 'No valid messages found in the uploaded files'}), 400
        
    # Combine all decoded messages
    full_message = ''.join(decoded_messages)
    
    # Check if it's an image
    if full_message.startswith('IMG:'):
        try:
            img = reconstruct_image(full_message)
            # Convert image to base64 for display
            buffered = BytesIO()
            img.save(buffered, format="PNG")
            img_base64 = base64.b64encode(buffered.getvalue()).decode()
            return jsonify({
                'type': 'image',
                'data': img_base64
            })
        except ValueError as e:
            return jsonify({'error': str(e)}), 400
    
    # Return as text if not an image
    return jsonify({
        'type': 'text',
        'message': full_message
    })

@app.route('/capacity')
def get_capacity():
    max_moves = calculate_max_moves()
    chars_per_game = (max_moves // 8) // 4  # Account for UTF-8's max 4 bytes per char
    return jsonify({
        'max_moves_per_game': max_moves,
        'max_chars_per_game': chars_per_game,
        'recommended_chunk_size': chars_per_game - 2  # Leave some margin
    })

if __name__ == '__main__':
    os.makedirs('output', exist_ok=True)
    app.run(debug=True, port=5001) 