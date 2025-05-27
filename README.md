# Hexago - Steganography with Go Game Files

Hexago is a web-based steganography tool that hides secret messages and images within valid Go game SGF files. The encoded files can be opened in any Go game viewer while secretly containing your hidden content.

## Features

- **Text Encoding**: Hide text messages, including special characters and emojis
- **Image Encoding**: Hide images (automatically resized to 64x64 pixels)
- **Multi-File Support**: Automatically splits large content across multiple game files
- **Valid SGF Files**: All generated files are valid Go game records
- **UTF-8 Support**: Full support for international characters and emojis
- **Web Interface**: Clean, modern UI for easy encoding and decoding

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/hexago.git
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
   - Select the "Text Message" tab to encode text
   - Select the "Image" tab to encode images
   - Click "Generate Go Games" to get your encoded SGF files

4. To decode content:
   - Upload the SGF file(s) in the decode section
   - Click "Decode Files" to reveal the hidden content

## Technical Details

- **Board Size**: 19x19 standard Go board
- **Encoding Method**: Uses black stones for 1s, white stones for 0s
- **Maximum Capacity**: 
  - Text: ~22 characters per game file (UTF-8 encoded)
  - Images: Automatically resized to 64x64 pixels
- **File Format**: Standard SGF (Smart Game Format)
- **Supported Image Types**: PNG, JPG, JPEG, GIF

## Dependencies

- Flask 3.0.2
- Pillow 11.2.1
- Werkzeug 3.0.1
- NumPy 2.2.6

## Security Considerations

- The tool uses standard steganography techniques
- The encoded messages are not encrypted
- For sensitive data, consider encrypting the message before encoding

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