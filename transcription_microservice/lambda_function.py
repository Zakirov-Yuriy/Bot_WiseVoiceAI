import json
import logging
import os
import tempfile
import asyncio
import boto3
import httpx
from botocore.exceptions import ClientError
from typing import Dict, List, Any, Optional

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Constants
ASSEMBLYAI_BASE_URL = "https://api.assemblyai.com/v2"
ASSEMBLYAI_API_KEY = os.environ.get('ASSEMBLYAI_API_KEY')
S3_BUCKET = os.environ.get('S3_BUCKET')

# AWS clients
s3_client = boto3.client('s3')

# Headers for AssemblyAI
HEADERS = {"authorization": ASSEMBLYAI_API_KEY}


class Segment(TypedDict):
    speaker: str
    text: str


async def upload_to_assemblyai(file_path: str, retries: int = 3) -> str:
    """Upload file to AssemblyAI"""
    for attempt in range(retries):
        try:
            async with httpx.AsyncClient() as client:
                with open(file_path, "rb") as f:
                    response = await client.post(
                        f"{ASSEMBLYAI_BASE_URL}/upload",
                        headers=HEADERS,
                        files={"file": f},
                        timeout=300
                    )
                response.raise_for_status()
                return response.json()["upload_url"]
        except Exception as e:
            logger.warning(f"Upload attempt {attempt + 1} failed: {str(e)}")
            if attempt == retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)


async def transcribe_with_assemblyai(audio_url: str, retries: int = 3) -> Dict[str, Any]:
    """Transcribe audio using AssemblyAI"""
    headers = {
        "authorization": HEADERS['authorization'],
        "content-type": "application/json"
    }
    payload = {
        "audio_url": audio_url,
        "speaker_labels": True,
        "punctuate": True,
        "format_text": True,
        "language_detection": True
    }

    for attempt in range(retries):
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{ASSEMBLYAI_BASE_URL}/transcript",
                    headers=headers, json=payload
                )
                resp.raise_for_status()
                transcript_id = resp.json()["id"]

                # Poll for completion
                while True:
                    status_resp = await client.get(
                        f"{ASSEMBLYAI_BASE_URL}/transcript/{transcript_id}",
                        headers=headers
                    )
                    result = status_resp.json()

                    if result["status"] == "completed":
                        return result
                    elif result["status"] == "error":
                        raise Exception(result["error"])

                    await asyncio.sleep(3)

        except Exception as e:
            logger.warning(f"Transcription attempt {attempt + 1} failed: {str(e)}")
            if attempt == retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)


def save_result_to_s3(file_id: str, result: Dict[str, Any]) -> None:
    """Save transcription result to S3"""
    result_key = f"transcription/results/{file_id}.json"

    try:
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=result_key,
            Body=json.dumps(result, ensure_ascii=False),
            ContentType='application/json'
        )
        logger.info(f"Result saved to S3: {result_key}")
    except ClientError as e:
        logger.error(f"Failed to save result to S3: {e}")
        raise


async def process_transcription(s3_key: str, user_id: int, file_id: str) -> Dict[str, Any]:
    """Main transcription processing logic"""
    temp_file = None

    try:
        # Download file from S3
        logger.info(f"Downloading file from S3: {s3_key}")
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.mp3')
        s3_client.download_file(S3_BUCKET, s3_key, temp_file.name)
        temp_file.close()

        # Upload to AssemblyAI
        logger.info("Uploading to AssemblyAI")
        audio_url = await upload_to_assemblyai(temp_file.name)

        # Transcribe
        logger.info("Starting transcription")
        result = await transcribe_with_assemblyai(audio_url)

        # Extract segments
        segments = []
        if "utterances" in result and result["utterances"]:
            for utt in result["utterances"]:
                segments.append({
                    "speaker": utt.get("speaker", "?"),
                    "text": (utt.get("text") or "").strip()
                })
        elif "text" in result:
            segments.append({"speaker": "?", "text": (result["text"] or "").strip()})

        # Prepare result
        final_result = {
            "status": "completed",
            "file_id": file_id,
            "user_id": user_id,
            "segments": segments,
            "metadata": {
                "total_segments": len(segments),
                "processing_time": result.get("processing_time", 0)
            }
        }

        logger.info(f"Transcription completed: {len(segments)} segments")
        return final_result

    except Exception as e:
        logger.error(f"Transcription failed: {str(e)}")
        return {
            "status": "error",
            "file_id": file_id,
            "user_id": user_id,
            "error": str(e)
        }

    finally:
        # Cleanup temp file
        if temp_file and os.path.exists(temp_file.name):
            try:
                os.unlink(temp_file.name)
            except:
                pass


def lambda_handler(event, context):
    """AWS Lambda handler"""
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        # Extract parameters
        s3_key = event.get('s3_key')
        user_id = event.get('user_id')
        file_id = event.get('file_id')
        bucket = event.get('bucket', S3_BUCKET)

        if not all([s3_key, user_id, file_id]):
            raise ValueError("Missing required parameters: s3_key, user_id, file_id")

        # Override bucket if provided
        global S3_BUCKET
        if bucket:
            S3_BUCKET = bucket

        # Process transcription asynchronously
        loop = asyncio.get_event_loop()
        result = loop.run_until_complete(process_transcription(s3_key, user_id, file_id))

        # Save result to S3
        save_result_to_s3(file_id, result)

        logger.info(f"Lambda execution completed for file_id: {file_id}")
        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Transcription completed", "file_id": file_id})
        }

    except Exception as e:
        logger.error(f"Lambda execution failed: {str(e)}")

        # Try to save error result
        try:
            error_result = {
                "status": "error",
                "file_id": event.get('file_id', 'unknown'),
                "user_id": event.get('user_id', 'unknown'),
                "error": str(e)
            }
            if 'file_id' in event:
                save_result_to_s3(event['file_id'], error_result)
        except:
            pass

        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }
