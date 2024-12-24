import os
import re
import  logging
import subprocess
import requests
import chardet
from pathlib import Path

logger = logging.getLogger(__name__)

class AudioProcessor:
    def __init__(self, apiKey, outputDir):
        self.apiKey = apiKey
        self.outputDir = Path(outputDir)
        self.outputDir.mkdir(parents=True, exist_ok=True)
    
    def createTranscription(self, audioFile):
        """Creates a transcription of the audio file using OpenAI's API."""
        try:
            url = "https://api.openai.com/v1/audio/transcriptions"
            headers = {
                "Authorization": f"Bearer {self.apiKey}",
            }
            with open(audioFile, 'rb') as audio:
                files = {
                    'file': ('audio.mp3', audio, 'audio/mpeg')
                }
                data = {
                    'model': 'whisper-1',
                    'response_format': 'srt'
                }
                response = requests.post(url, headers=headers, files=files, data=data)
            if response.status_code == 200:
                # Save the generated SRT file in the clips directory
                srtFilePath = os.path.join(self.outputDir, f"{os.path.splitext(os.path.basename(audioFile))[0]}.srt")
                with open(srtFilePath, 'w', encoding='utf-8') as srtFile:
                    srtFile.write(response.text)
                return srtFilePath
            else:
                logger.error(f"Error creating transcription: {response.text}")
                return None
        except Exception as e:
            logger.error(f"Error in createTranscription: {e}")
            return None


    def extractAudioFromVideo(self, videoFile):
        """Extracts audio from the video file and returns the audio file path as .mp3."""
        audioFile = os.path.join(self.outputDir, f"{os.path.splitext(os.path.basename(videoFile))[0]}.mp3")
        command = ['ffmpeg', '-y', '-i', videoFile, '-q:a', '0', '-map', 'a', audioFile]
        subprocess.run(command, check=True)
        return audioFile

    def adjustTime(self, timestamp, offset):
        """Adjusts the timestamp by a given offset in seconds."""
        try:
            timestamp = timestamp.replace(',', '.')
            timeParts = timestamp.split(':')
            hours = int(timeParts[0])
            minutes = int(timeParts[1])
            seconds = float(timeParts[2])
            totalSeconds = hours * 3600 + minutes * 60 + seconds + offset
            if totalSeconds < 0:
                totalSeconds = 0
            hours = int(totalSeconds // 3600)
            minutes = int((totalSeconds % 3600) // 60)
            seconds = totalSeconds % 60
            return f"{hours:02d}:{minutes:02d}:{seconds:06.3f}".replace('.', ',')
        except Exception as e:
            print(f"Error adjusting timestamp: {e}")
            return timestamp

    def extractTimestamps(self, srtFile, queryWord, contextLines=2):
        """Extracts timestamps from the SRT file based on the query word with context."""
        timestamps = []
        try:
            # Detect encoding
            with open(srtFile, 'rb') as file:
                raw_data = file.read()
                result = chardet.detect(raw_data)
                encoding = result['encoding'] if result['confidence'] > 0.5 else None
            
            # Attempt to read the file with detected encoding
            encodings_to_try = [encoding, 'utf-8', 'ISO-8859-1', 'Windows-1252']
            for enc in encodings_to_try:
                try:
                    if enc is not None:
                        with open(srtFile, 'r', encoding=enc) as file:
                            content = file.read()
                    else:
                        # If encoding is None, skip to the next encoding
                        continue
                    
                    # Process the content
                    blocks = content.split('\n\n')
                    for i, block in enumerate(blocks):
                        if queryWord.lower() in block.lower():
                            lines = block.split('\n')
                            if len(lines) >= 2:
                                timestampLine = next((line for line in lines if ' --> ' in line), None)
                                if timestampLine:
                                    match = re.search(r'(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})', timestampLine)
                                    if match:
                                        start = match.group(1)
                                        end = match.group(2)
                                        contextStart = start
                                        contextEnd = end
                                        if i > 0:
                                            prevBlock = blocks[i-1]
                                            prevTimestamp = re.search(r'(\d{2}:\d{2}:\d{2},\d{3}) -->', prevBlock)
                                            if prevTimestamp:
                                                contextStart = prevTimestamp.group(1)
                                        if i < len(blocks) - 1:
                                            nextBlock = blocks[i+1]
                                            nextTimestamp = re.search(r'--> (\d{2}:\d{2}:\d{2},\d{3})', nextBlock)
                                            if nextTimestamp:
                                                contextEnd = nextTimestamp.group(1)
                                        timestamps.append((contextStart, contextEnd))
                    break  # Exit the loop if reading was successful
                except (UnicodeDecodeError, TypeError) as e:
                    print(f"Failed to decode with {enc}: {e}. Trying next encoding.")
        except Exception as e:
            print(f"Error extracting timestamps: {e}")
        return timestamps

    def extractVideoClips(self, videoFile, timestamps):
        """Extracts video clips based on the provided timestamps."""
        extractedClips = []
        for i, (start, end) in enumerate(timestamps):
            outputClip = os.path.join(self.outputDir, f'clip{i+1}.mp4')
            try:
                command = [
                    'ffmpeg', '-y', '-ss', start.replace(',', '.'), 
                    '-to', end.replace(',', '.'), 
                    '-i', videoFile, 
                    '-c', 'copy', 
                    outputClip
                ]
                subprocess.run(command, check=True)
                extractedClips.append(outputClip)
            except subprocess.CalledProcessError as e:
                print(f"Error extracting clip {i+1}: {e}")
                continue
                
        return extractedClips

    def splitAudioIntoChunks(self, audioFile, chunkLength=1200):
        """Splits the audio file into smaller chunks if it's longer than the specified length."""
        try:
            durationCommand = ['ffprobe', '-v', 'error', '-show_entries', 
                             'format=duration', '-of', 
                             'default=noprint_wrappers=1:nokey=1', audioFile]
            duration = float(subprocess.check_output(durationCommand).strip())
            if duration <= chunkLength:
                return [audioFile]
            baseName = os.path.splitext(audioFile)[0]
            chunkFiles = []
            command = [
                'ffmpeg', '-y', '-i', audioFile, 
                '-f', 'segment', 
                '-segment_time', str(chunkLength),
                '-c', 'copy', 
                f"{baseName}_chunk%03d.mp3"
            ]
            subprocess.run(command, check=True)
            for i in range(1000):
                chunkFile = f"{baseName}_chunk{i:03d}.mp3"
                if os.path.exists(chunkFile):
                    chunkFiles.append(chunkFile)
                else:
                    break
            return chunkFiles
        except Exception as e:
            print(f"Error splitting audio into chunks: {e}")
            return [audioFile]

    def createFinalReel(self, clipFiles, outputFile):
        """Merges the extracted clips into a final video file."""
        with open('mylist.txt', 'w') as f:
            for clip in clipFiles:
                f.write(f"file '{clip}'\n")
        mergeCommand = [
            'ffmpeg', '-f', 'concat', '-safe', '0', '-i', 'mylist.txt', '-c', 'copy', outputFile
        ]
        subprocess.run(mergeCommand, check=True)
        print(f'Merged clips into {outputFile}')

    def mergeExtractedClips(self, outputFile):
        """Merges all extracted clips and adds new subtitles to the final output."""
        clipFiles = [os.path.join(self.outputDir, f) for f in os.listdir(self.outputDir) if f.endswith('.mp4')]
        if not clipFiles:
            logger.error("No clips found to merge.")
            return None

        # Merge all clips into a single video
        self.createFinalReel(clipFiles, outputFile)
        logger.info(f"Merged clips into: {outputFile}")

        # Extract audio from the merged video
        mergedAudioFile = self.extractAudioFromVideo(outputFile)
        logger.info(f"Extracted audio from merged video: {mergedAudioFile}")

        # Generate new subtitles for the merged video
        newSrtFilePath = self.createTranscription(mergedAudioFile)
        if not newSrtFilePath:
            logger.error("Failed to generate new subtitles for merged video.")
            return None
        logger.info(f"Generated new subtitles: {newSrtFilePath}")

        # Add new subtitles to the merged video
        try:
            self.addSubtitles(outputFile, newSrtFilePath)
            logger.info(f"Added new subtitles to final video: {outputFile}")
        except Exception as e:
            logger.error(f"Error adding subtitles to final video: {e}")
            return None
        return outputFile  # Return the final video path

    def addSubtitles(self, video_file, srtFilePath, outputFilePath):
        """Adds subtitles to the final video."""
        temp_output = Path(f"{outputFilePath}_temp.mp4")

        # Ensure paths are compatible with FFmpeg
        video_file = str(video_file).replace("\\", "/")
        srtFilePath = str(srtFilePath).replace("\\", "/")
        outputFilePath = str(outputFilePath).replace("\\", "/")

        command = [
            'ffmpeg', '-i', video_file, '-vf', f"subtitles={srtFilePath}", '-c:a', 'copy', outputFilePath
        ]
        try:
            subprocess.run(command, check=True)
            logger.info(f"Subtitles added successfully to: {outputFilePath}")
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e}")
            raise
