# AI Video Generator

This project uses AI to generate videos from text topics. It combines:
- GPT-4 for script generation
- OpenAI TTS for audio narration
- Stable Diffusion for video frame generation
- MoviePy for video assembly

## Setup

1. Install the required dependencies:
```bash
pip install -r requirements.txt
```

2. Create a `.env` file in the project root with your API keys:
```
OPENAI_API_KEY=your_openai_api_key
REPLICATE_API_TOKEN=your_replicate_api_token
```

## Usage

Run the script with a topic of your choice:
```bash
python main.py
```

By default, it will generate a video about "The future of artificial intelligence". You can modify the topic in the `main.py` file.

## Output

The generated video will be saved in the `output` directory as `final_video.mp4`. The process includes:
1. Generating a script (max 1000 characters)
2. Converting the script to audio
3. Generating video frames using Stable Diffusion
4. Combining everything into a final video

## Requirements

- Python 3.7+
- OpenAI API key
- Replicate API token
- Sufficient disk space for video generation