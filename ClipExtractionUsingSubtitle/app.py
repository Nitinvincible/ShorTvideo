import os
from pathlib import Path
from flask import Flask, request, render_template, send_from_directory
from audioProcessor import AudioProcessor
import time
import logging

# Configure the logger
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%d/%b/%Y %H:%M:%S'
)
logger = logging.getLogger(__name__)  # Properly configured logger

# Define the base directory for all file operations
BASE_DIR = Path("/home/indevznitin/indevzcodekali/ClipExtractionUsingSubtitle")
CLIPS_DIR = BASE_DIR / "clips"

# Ensure the clips directory exists
CLIPS_DIR.mkdir(parents=True, exist_ok=True)

app = Flask(__name__)
audioProcessor = AudioProcessor(apiKey="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", outputDir=CLIPS_DIR)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload():
    videoPath = None
    finalOutputFile = None
    try:
        if 'videoFile' not in request.files:
            return "No file part", 400

        videoFile = request.files['videoFile']
        keyword = request.form.get('keyword', '')
        addSubtitlesFlag = request.form.get('addSubtitles', 'off') == 'on'
        logger.info(f"Received keyword: {keyword}, addSubtitles: {addSubtitlesFlag}")

        if videoFile.filename == '':
            return "No selected file", 400

        # Save video file in a temporary location within BASE_DIR
        videoPath = BASE_DIR / f"temp_upload_{int(time.time())}.mp4"
        videoFile.save(videoPath)

        # Extract audio and generate transcription for clip extraction
        audioFile = audioProcessor.extractAudioFromVideo(videoPath)
        transcriptionPath = audioProcessor.createTranscription(audioFile)

        if not transcriptionPath:
            logger.error("Failed to generate transcription.")
            return "No SRT file generated.", 400

        # Extract timestamps from SRT file
        allTimestamps = audioProcessor.extractTimestamps(transcriptionPath, keyword)
        if not allTimestamps:
            return "No timestamps found for the given keyword.", 400

        # Extract video clips and merge them into a final output
        extractedClips = audioProcessor.extractVideoClips(videoPath, allTimestamps)
        finalOutputFile = CLIPS_DIR / f"final_output_{int(time.time())}.mp4"
        audioProcessor.createFinalReel(extractedClips, finalOutputFile)

        # Generate subtitles for the final merged video
        mergedAudioFile = audioProcessor.extractAudioFromVideo(finalOutputFile)
        newSrtFilePath = audioProcessor.createTranscription(mergedAudioFile)

        if addSubtitlesFlag and newSrtFilePath:
            # Add subtitles to the final merged video
            finalOutputWithSubtitles = CLIPS_DIR / f"{finalOutputFile.stem}_with_subtitles.mp4"
            audioProcessor.addSubtitles(finalOutputFile, newSrtFilePath, finalOutputWithSubtitles)
            finalOutputFile = finalOutputWithSubtitles

        return render_template('index.html', finalVideo=finalOutputFile.name)
    except Exception as e:
        logger.error(f"An error occurred: {e}")
        return "An error occurred during processing.", 500
    finally:
        if videoPath and videoPath.exists():
            videoPath.unlink()

@app.route('/clips/<path:filename>')
def sendClip(filename):
    return send_from_directory(CLIPS_DIR, filename)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
