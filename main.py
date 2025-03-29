import os
from dotenv import load_dotenv
import openai
import replicate
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_videoclips
import asyncio
from pathlib import Path
import json
import requests
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('video_generator.log'),
        logging.StreamHandler()
    ]
)

# Load environment variables
load_dotenv(override=True)

# Configure OpenAI
api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise ValueError("OPENAI_API_KEY not found in environment variables")
openai.api_key = api_key

# Configure Replicate
replicate_token = os.getenv("REPLICATE_API_TOKEN")
if not replicate_token:
    raise ValueError("REPLICATE_API_TOKEN not found in environment variables")
os.environ["REPLICATE_API_TOKEN"] = replicate_token

# Get the project root directory
PROJECT_ROOT = Path(__file__).parent.absolute()

def create_output_directory(topic):
    """Create a timestamped directory for the video project"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_topic = "".join(c for c in topic if c.isalnum() or c in (' ', '-', '_')).rstrip()
    project_dir = PROJECT_ROOT / "output" / f"{timestamp}_{safe_topic}"
    project_dir.mkdir(parents=True, exist_ok=True)
    logging.info(f"Created output directory: {project_dir}")
    return project_dir

def generate_script(topic):
    """Generate a script using GPT-4"""
    logging.debug(f"Generating script for topic: {topic}")
    prompt = f"""Create a short, engaging script about {topic}. The script should be:
    1. Maximum 1000 characters
    2. Easy to understand
    3. Suitable for video narration
    4. Include clear scene descriptions for image generation
    
    Format the response as JSON with:
    - "script": The narration text
    - "scenes": List of scene descriptions for image generation
    """
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a creative scriptwriter."},
                {"role": "user", "content": prompt}
            ]
        )
        
        content = json.loads(response.choices[0].message.content)
        logging.debug(f"Generated script: {content['script'][:100]}...")
        logging.debug(f"Generated {len(content['scenes'])} scenes")
        return content
    except Exception as e:
        logging.error(f"Error generating script: {str(e)}")
        raise

def generate_audio(script, output_dir):
    """Generate audio from script using OpenAI TTS"""
    output_path = output_dir / "narration.mp3"
    logging.debug(f"Generating audio for script: {script[:100]}...")
    
    try:
        response = openai.audio.speech.create(
            model="tts-1",
            voice="alloy",
            input=script
        )
        
        response.stream_to_file(str(output_path))
        logging.debug(f"Audio generated successfully: {output_path}")
        return output_path
    except Exception as e:
        logging.error(f"Error generating audio: {str(e)}")
        raise

def generate_video_frames(scenes, output_dir):
    """Generate video frames using Stable Diffusion"""
    frames = []
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(exist_ok=True)
    
    logging.debug(f"Generating {len(scenes)} video frames")
    
    for i, scene in enumerate(scenes):
        output_path = frames_dir / f"frame_{i}.png"
        logging.debug(f"Generating frame {i+1}/{len(scenes)}: {scene[:50]}...")
        
        try:
            # Run Stable Diffusion model
            output = replicate.run(
                "stability-ai/stable-diffusion:db21e45d3f7023abc2a46ee38a23973f6dce16bb082a930b0c49861f96d1e5bf",
                input={
                    "prompt": scene,
                    "negative_prompt": "blurry, low quality, distorted",
                    "num_outputs": 1,
                    "guidance_scale": 7.5,
                    "num_inference_steps": 50,
                    "scheduler": "K_EULER",
                    "width": 1024,
                    "height": 576
                }
            )
            
            # Download the generated image
            response = requests.get(output[0])
            with open(output_path, "wb") as f:
                f.write(response.content)
            
            frames.append(output_path)
            logging.debug(f"Frame {i+1} generated successfully")
        except Exception as e:
            logging.error(f"Error generating frame {i+1}: {str(e)}")
            raise
    
    return frames

def create_video(frames, audio_path, output_path):
    """Create final video by combining frames and audio"""
    logging.debug(f"Creating final video with {len(frames)} frames")
    
    try:
        # Create video from frames
        clips = []
        for frame_path in frames:
            clip = VideoFileClip(str(frame_path)).set_duration(3)  # Each frame shows for 3 seconds
            clips.append(clip)
        
        video = concatenate_videoclips(clips)
        
        # Add audio
        audio = AudioFileClip(str(audio_path))
        final_video = video.set_audio(audio)
        
        # Write final video
        final_video.write_videofile(
            str(output_path),
            fps=24,
            codec='libx264',
            audio_codec='aac'
        )
        
        # Clean up
        video.close()
        audio.close()
        
        logging.debug(f"Final video created successfully: {output_path}")
    except Exception as e:
        logging.error(f"Error creating video: {str(e)}")
        raise

def save_project_info(output_dir, topic, script, scenes):
    """Save project information to a JSON file"""
    info = {
        "topic": topic,
        "timestamp": datetime.now().isoformat(),
        "script": script,
        "scenes": scenes
    }
    
    info_path = output_dir / "project_info.json"
    with open(info_path, "w") as f:
        json.dump(info, f, indent=2)
    logging.debug(f"Project info saved to: {info_path}")

async def generate_video(topic):
    """Main function to generate the complete video"""
    logging.info(f"Starting video generation for topic: {topic}")
    
    # Create output directory
    output_dir = create_output_directory(topic)
    
    try:
        # Generate script
        logging.info("Generating script...")
        content = generate_script(topic)
        script = content["script"]
        scenes = content["scenes"]
        
        # Save project info
        save_project_info(output_dir, topic, script, scenes)
        
        # Generate audio
        logging.info("Generating audio...")
        audio_path = generate_audio(script, output_dir)
        
        # Generate video frames
        logging.info("Generating video frames...")
        frames = generate_video_frames(scenes, output_dir)
        
        # Create final video
        logging.info("Creating final video...")
        output_path = output_dir / "final_video.mp4"
        create_video(frames, audio_path, output_path)
        
        logging.info(f"✨ Video generated successfully! Output: {output_path}")
        return output_path
    except Exception as e:
        logging.error(f"Error in video generation: {str(e)}")
        raise

def test_video_generation():
    """Test function to verify video generation with a short topic"""
    test_topic = "A sunset over mountains"
    logging.info("Starting test video generation")
    
    try:
        asyncio.run(generate_video(test_topic))
        logging.info("Test completed successfully")
    except Exception as e:
        logging.error(f"Test failed: {str(e)}")
        raise

if __name__ == "__main__":
    # Run test first
    logging.info("Running test video generation...")
    test_video_generation()
    
    # Generate main video
    topic = "The future of artificial intelligence"
    asyncio.run(generate_video(topic))
