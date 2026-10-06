# Hexago - Steganography with Go Game Files

Hexago is a web-based steganography tool that hides secret messages and images within valid Go game SGF files. The encoded files can be opened in any Go game viewer while secretly containing your hidden content.

## Features

- **Text Encoding**: Hide text messages, including special characters and emojis
- **Image Encoding**: Hide images (automatically resized to fit 64x64 pixels)
- **Multi-File Support**: Automatically splits large content across multiple game files, which can be decoded in any order
- **Valid SGF Files**: All generated files are valid Go game records
- **UTF-8 Support**: Full support for international characters and emojis
- **Web Interface**: Clean, modern UI for easy encoding and decoding

## Installation

Requires Python 3.10 or newer.

1. Clone the repository:
   ```bash
   git clone https://github.com/dumbanshm/hexago.git
   cd hexago
   ```

2. Create and activate a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Start the server:
   ```bash
   python app.py
   ```

2. Open your browser and navigate to:
   ```
   http://localhost:5001
   ```

3. To encode content:
   - Choose Text or Image and enter your message or pick an image
   - The board previews each game as you type; click a game number to see its board
   - Click "Download games (.zip)" to get your encoded SGF files

4. To decode content:
   - Switch to Decode and drop in all the SGF files, in any order
   - The hidden message or image appears on the right

## Technical Details

- **Board Size**: 19x19 standard Go board
- **Encoding Method**: Content is zlib-compressed when that makes it smaller (short messages are stored as is), then stored one bit per stone (black = 1, white = 0), filling all 361 points of the board in a spiral from the center
- **Capacity**: 45 bytes per game file
  - Text: short messages fit about 43 characters in one game; longer English text compresses to about 60 characters per game
  - Images: resized to fit 64x64 pixels and stored as WebP; usually 2-15 game files
- **File Order**: Each game's name (`GN[hexago 3/12]`) records its position, so files can be uploaded in any order
- **Limits**: Uploads are capped at 5 MB
- **File Format**: Standard SGF (Smart Game Format)
- **Supported Image Types**: PNG, JPG, JPEG, GIF

## Dependencies

- Flask 3.1.3
- Pillow 12.3.0
- Werkzeug 3.1.9

## Development

Run the tests:
```bash
pip install -r requirements-dev.txt
pytest
```

Flask's debug mode is off by default. Turn it on only on your own machine with `FLASK_DEBUG=1 python app.py`.

## Security Considerations

- The tool uses standard steganography techniques
- The encoded messages are not encrypted
- For sensitive data, consider encrypting the message before encoding
- The stone pattern is not a realistic game, and viewers that apply capture rules will remove some stones when replaying it; the hidden data is read from the file itself and is unaffected
- Files made by versions before this format change cannot be decoded

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Acknowledgments

- Inspired by the game of Go and its SGF format
- Built with Flask and modern web technologies
- Special thanks to the Go/Baduk community 