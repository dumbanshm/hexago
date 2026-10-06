import base64
import io
import random
import re
import zipfile

import pytest
from PIL import Image

import app as hexago


@pytest.fixture
def client():
    return hexago.app.test_client()


def random_text(length, seed=0):
    rng = random.Random(seed)
    return ''.join(rng.choice('abcdefghijklmnopqrstuvwxyz ') for _ in range(length))


def encode_text(client, message):
    response = client.post('/encode', json={'message': message})
    assert response.status_code == 200
    return zipfile.ZipFile(io.BytesIO(response.data))


def encode_image(client, img, filename='image.png'):
    buffered = io.BytesIO()
    img.save(buffered, format='PNG')
    buffered.seek(0)
    response = client.post('/encode', data={'image': (buffered, filename)},
                           content_type='multipart/form-data')
    assert response.status_code == 200
    return zipfile.ZipFile(io.BytesIO(response.data))


def decode(client, archive, names=None):
    names = archive.namelist() if names is None else names
    files = [(io.BytesIO(archive.read(name)), name) for name in names]
    return client.post('/decode', data={'file': files}, content_type='multipart/form-data')


def test_board_path_covers_every_point_once():
    assert len(hexago.BOARD_PATH) == 361
    assert len(set(hexago.BOARD_PATH)) == 361


def test_sgf_is_well_formed(client):
    archive = encode_text(client, 'hello')
    sgf = archive.read(archive.namelist()[0]).decode()
    assert sgf.startswith('(;GM[1]FF[4]SZ[19]')
    assert sgf.endswith(')')
    # Exactly one game tree: the only closing paren is the last character
    assert sgf.count(')') == 1


@pytest.mark.parametrize('message', [
    'Hello world',
    'héllo 🎉 ' * 10,
    'line one\nline two',
])
def test_text_round_trip(client, message):
    archive = encode_text(client, message)
    response = decode(client, archive)
    assert response.json == {'type': 'text', 'message': message}


def test_decode_is_order_independent(client):
    message = random_text(2000)
    archive = encode_text(client, message)
    names = archive.namelist()
    assert len(names) >= 10
    random.Random(0).shuffle(names)
    assert decode(client, archive, names).json['message'] == message


def test_zip_names_sort_in_game_order(client):
    archive = encode_text(client, random_text(2000))
    names = archive.namelist()
    assert len(names) >= 10
    assert names == sorted(names)


def test_missing_game_is_reported(client):
    archive = encode_text(client, random_text(2000))
    names = archive.namelist()[1:]
    response = decode(client, archive, names)
    assert response.status_code == 400
    assert 'Missing' in response.json['error']


def test_image_round_trip(client):
    img = Image.new('RGB', (200, 150), (200, 30, 30))
    archive = encode_image(client, img)
    response = decode(client, archive)
    assert response.json['type'] == 'image'
    decoded = Image.open(io.BytesIO(base64.b64decode(response.json['data'])))
    assert decoded.size == (64, 48)


def test_noisy_image_needs_few_games(client):
    rng = random.Random(1)
    img = Image.new('RGB', (400, 400))
    img.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256)) for _ in range(400 * 400)])
    archive = encode_image(client, img)
    assert len(archive.namelist()) < 100
    assert decode(client, archive).json['type'] == 'image'


def test_non_utf8_sgf_is_rejected(client):
    files = [(io.BytesIO(b'\xff\xfe'), 'bad.sgf')]
    response = client.post('/decode', data={'file': files}, content_type='multipart/form-data')
    assert response.status_code == 400


def test_foreign_sgf_is_rejected(client):
    files = [(io.BytesIO(b'(;GM[1]FF[4]SZ[19];B[aa];W[bb])'), 'game.sgf')]
    response = client.post('/decode', data={'file': files}, content_type='multipart/form-data')
    assert response.status_code == 400


def test_oversized_upload_is_rejected(client):
    files = [(io.BytesIO(b'a' * (6 * 1024 * 1024)), 'big.sgf')]
    response = client.post('/decode', data={'file': files}, content_type='multipart/form-data')
    assert response.status_code == 413


def test_debug_mode_is_off_by_default():
    assert hexago.app.debug is False


def test_short_text_is_stored_uncompressed():
    payload = hexago.build_payload(hexago.TYPE_TEXT, b'North gate at dawn. Bring the second key.')
    assert payload[:1] == hexago.STORED_RAW
    assert len(hexago.encode_payload(payload)) == 1


def test_compressible_text_is_compressed(client):
    message = 'ab' * 500
    payload = hexago.build_payload(hexago.TYPE_TEXT, message.encode())
    assert payload[:1] == hexago.STORED_ZLIB
    assert decode(client, encode_text(client, message)).json['message'] == message


def test_preview_matches_encode(client):
    message = random_text(300)
    preview = client.post('/preview', json={'message': message}).json
    archive = encode_text(client, message)
    assert preview['games'] == [archive.read(name).decode() for name in archive.namelist()]
    assert preview['bytes_per_game'] == 45
    assert preview['payload_bytes'] > 0


def test_preview_rejects_empty_message(client):
    response = client.post('/preview', json={'message': ''})
    assert response.status_code == 400


def test_huge_image_dimensions_are_rejected(client):
    # A tiny file that declares a 10000 x 10000 bitmap
    img = Image.new('1', (10000, 10000))
    buffered = io.BytesIO()
    img.save(buffered, format='PNG')
    assert len(buffered.getvalue()) < 5 * 1024 * 1024
    buffered.seek(0)
    response = client.post('/encode', data={'image': (buffered, 'bomb.png')},
                           content_type='multipart/form-data')
    assert response.status_code == 400


def test_fonts_are_served_locally(client):
    page = client.get('/').get_data(as_text=True)
    assert 'googleapis' not in page and 'gstatic' not in page
    css = client.get('/fonts/fonts.css')
    assert css.status_code == 200
    for name in re.findall(r'url\(([^)]+)\)', css.get_data(as_text=True)):
        assert client.get(f'/fonts/{name}').status_code == 200


def test_conflicting_games_are_rejected(client):
    first = encode_text(client, 'first secret')
    second = encode_text(client, 'second secret')
    files = [(io.BytesIO(first.read(first.namelist()[0])), 'a.sgf'),
             (io.BytesIO(second.read(second.namelist()[0])), 'b.sgf')]
    response = client.post('/decode', data={'file': files}, content_type='multipart/form-data')
    assert response.status_code == 400
    assert 'different encodings' in response.json['error']


def test_transparent_image_is_put_on_white(client):
    img = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
    archive = encode_image(client, img)
    response = decode(client, archive)
    decoded = Image.open(io.BytesIO(base64.b64decode(response.json['data']))).convert('RGB')
    assert min(decoded.getpixel((16, 16))) > 240


def test_malformed_json_is_a_client_error(client):
    response = client.post('/encode', data='{bad', content_type='application/json')
    assert response.status_code == 400
    assert 'error' in response.json


def test_credits_page(client):
    assert 'href="/credits"' in client.get('/').get_data(as_text=True)
    response = client.get('/credits')
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert 'Devansh Mehta' in page
    assert 'googleapis' not in page and 'gstatic' not in page


def test_favicons_are_linked_and_served(client):
    for page in ('/', '/credits'):
        html = client.get(page).get_data(as_text=True)
        for href in re.findall(r'<link rel="(?:icon|apple-touch-icon)" href="([^"]+)"', html):
            assert client.get(href).status_code == 200
        assert 'href="/favicon.svg"' in html


def test_easter_egg_game_decodes(client):
    sgf = client.get('/easter-egg/lets-chat.sgf')
    assert sgf.status_code == 200
    response = client.post('/decode', data={'file': (io.BytesIO(sgf.data), 'lets-chat.sgf')},
                           content_type='multipart/form-data')
    assert response.status_code == 200
    assert response.get_json()['message'] == "Let's chat!"
