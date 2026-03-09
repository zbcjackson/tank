"""
Integration example: Using speaker identification in Tank backend.

This example shows how to integrate speaker identification into the
existing Perception pipeline for real-time speaker recognition.
"""

from __future__ import annotations

import logging

from tank_backend.audio.input.voiceprint_factory import create_voiceprint_recognizer
from tank_backend.plugin import AppConfig

logger = logging.getLogger(__name__)


class SpeakerAwarePerception:
    """
    Example integration of speaker identification into Perception.

    This shows how to use the voiceprint recognizer in a real-time
    audio processing pipeline.
    """

    def __init__(self, app_config: AppConfig):
        """
        Initialize speaker-aware perception.

        Args:
            app_config: Application configuration
        """
        self.app_config = app_config

        # Create voiceprint recognizer
        self.voiceprint = create_voiceprint_recognizer(app_config)

        # Track speaker statistics
        self.speaker_stats = {}

        logger.info("Speaker-aware perception initialized")

    def process_utterance(self, utterance) -> tuple[str, str]:
        """
        Process utterance with speaker identification.

        Args:
            utterance: Audio utterance to process

        Returns:
            Tuple of (user_id, transcribed_text)
        """
        # Identify speaker
        user_id = self.voiceprint.identify(utterance)

        # Update statistics
        if user_id not in self.speaker_stats:
            self.speaker_stats[user_id] = {"count": 0, "total_duration": 0.0}

        self.speaker_stats[user_id]["count"] += 1
        duration = utterance.ended_at_s - utterance.started_at_s
        self.speaker_stats[user_id]["total_duration"] += duration

        logger.info(
            f"Speaker identified: {user_id} "
            f"(utterance #{self.speaker_stats[user_id]['count']}, "
            f"duration={duration:.2f}s)"
        )

        # In real implementation, you would also run ASR here
        # For this example, we just return the user_id
        return user_id, ""

    def get_speaker_stats(self) -> dict:
        """Get speaker statistics."""
        return self.speaker_stats.copy()

    def close(self):
        """Clean up resources."""
        self.voiceprint.close()


# Example: Personalized responses based on speaker
class PersonalizedResponseGenerator:
    """
    Generate personalized responses based on identified speaker.

    This demonstrates how to use speaker identification to provide
    customized responses for different users.
    """

    def __init__(self):
        """Initialize response generator."""
        # User preferences (in real app, load from database)
        self.user_preferences = {
            "alice": {
                "language": "en",
                "formality": "casual",
                "interests": ["technology", "music"],
            },
            "bob": {
                "language": "zh",
                "formality": "formal",
                "interests": ["business", "finance"],
            },
            "charlie": {
                "language": "en",
                "formality": "casual",
                "interests": ["sports", "gaming"],
            },
        }

    def generate_greeting(self, user_id: str) -> str:
        """
        Generate personalized greeting.

        Args:
            user_id: Identified user ID

        Returns:
            Personalized greeting message
        """
        if user_id == "Unknown":
            return "Hello! How can I help you today?"

        prefs = self.user_preferences.get(user_id, {})
        language = prefs.get("language", "en")
        formality = prefs.get("formality", "casual")

        if language == "zh":
            if formality == "formal":
                return f"您好，{user_id}。有什么可以帮您的吗？"
            else:
                return f"嗨，{user_id}！今天怎么样？"
        else:
            if formality == "formal":
                return f"Good day, {user_id}. How may I assist you?"
            else:
                return f"Hey {user_id}! What's up?"

    def generate_response(self, user_id: str, query: str) -> str:
        """
        Generate personalized response based on user preferences.

        Args:
            user_id: Identified user ID
            query: User query

        Returns:
            Personalized response
        """
        if user_id == "Unknown":
            return self._generate_generic_response(query)

        prefs = self.user_preferences.get(user_id, {})
        interests = prefs.get("interests", [])

        # Customize response based on user interests
        # (In real app, this would use LLM with user context)
        response = f"Based on your interests in {', '.join(interests)}, "
        response += "I think you might find this helpful..."

        return response

    def _generate_generic_response(self, query: str) -> str:
        """Generate generic response for unknown users."""
        return "I'd be happy to help with that!"


# Example: Speaker enrollment workflow
class SpeakerEnrollmentWorkflow:
    """
    Workflow for enrolling new speakers.

    This demonstrates best practices for speaker enrollment,
    including multiple samples and quality checks.
    """

    def __init__(self, app_config: AppConfig):
        """Initialize enrollment workflow."""
        self.app_config = app_config
        self.voiceprint = create_voiceprint_recognizer(app_config)
        self.min_samples = 3
        self.max_samples = 5
        self.min_duration_s = 2.0
        self.max_duration_s = 10.0

    def enroll_speaker(
        self, user_id: str, name: str, audio_samples: list
    ) -> dict[str, any]:
        """
        Enroll a new speaker with quality checks.

        Args:
            user_id: Unique user identifier
            name: Display name
            audio_samples: List of (audio, sample_rate) tuples

        Returns:
            Enrollment result with status and details
        """
        result = {
            "success": False,
            "user_id": user_id,
            "name": name,
            "samples_enrolled": 0,
            "errors": [],
        }

        # Check minimum samples
        if len(audio_samples) < self.min_samples:
            result["errors"].append(
                f"Insufficient samples: need at least {self.min_samples}, got {len(audio_samples)}"
            )
            return result

        # Enroll each sample with quality checks
        enrolled_count = 0
        for i, (audio, sample_rate) in enumerate(audio_samples):
            # Check duration
            duration = len(audio) / sample_rate
            if duration < self.min_duration_s:
                result["errors"].append(
                    f"Sample {i+1} too short: {duration:.1f}s (min: {self.min_duration_s}s)"
                )
                continue

            if duration > self.max_duration_s:
                result["errors"].append(
                    f"Sample {i+1} too long: {duration:.1f}s (max: {self.max_duration_s}s)"
                )
                continue

            # Check audio quality (simple energy check)
            energy = (audio**2).mean()
            if energy < 0.001:
                result["errors"].append(f"Sample {i+1} too quiet (energy: {energy:.6f})")
                continue

            # Enroll sample
            try:
                self.voiceprint.enroll(user_id, name, audio, sample_rate)
                enrolled_count += 1
                logger.info(f"Enrolled sample {i+1}/{len(audio_samples)} for {user_id}")

                # Stop after max samples
                if enrolled_count >= self.max_samples:
                    break

            except Exception as e:
                result["errors"].append(f"Sample {i+1} enrollment failed: {e}")

        result["samples_enrolled"] = enrolled_count

        # Check if enrollment was successful
        if enrolled_count >= self.min_samples:
            result["success"] = True
            logger.info(
                f"Successfully enrolled {user_id} with {enrolled_count} samples"
            )
        else:
            result["errors"].append(
                f"Insufficient valid samples: enrolled {enrolled_count}, need {self.min_samples}"
            )

        return result

    def verify_enrollment(self, user_id: str, test_audio, sample_rate: int) -> dict:
        """
        Verify that enrollment was successful.

        Args:
            user_id: User ID to verify
            test_audio: Test audio sample
            sample_rate: Sample rate

        Returns:
            Verification result
        """
        from tank_backend.audio.input.voiceprint import Utterance

        utterance = Utterance(
            pcm=test_audio,
            sample_rate=sample_rate,
            started_at_s=0.0,
            ended_at_s=len(test_audio) / sample_rate,
        )

        identified_user = self.voiceprint.identify(utterance)

        result = {
            "expected": user_id,
            "identified": identified_user,
            "success": identified_user == user_id,
        }

        if result["success"]:
            logger.info(f"Enrollment verification successful for {user_id}")
        else:
            logger.warning(
                f"Enrollment verification failed: expected {user_id}, got {identified_user}"
            )

        return result

    def close(self):
        """Clean up resources."""
        self.voiceprint.close()


# Example: Multi-speaker conversation tracking
class ConversationTracker:
    """
    Track multi-speaker conversations.

    This demonstrates how to use speaker identification to track
    who said what in a conversation.
    """

    def __init__(self, app_config: AppConfig):
        """Initialize conversation tracker."""
        self.app_config = app_config
        self.voiceprint = create_voiceprint_recognizer(app_config)
        self.conversation_history = []

    def add_utterance(self, utterance, text: str):
        """
        Add utterance to conversation history.

        Args:
            utterance: Audio utterance
            text: Transcribed text
        """
        # Identify speaker
        user_id = self.voiceprint.identify(utterance)

        # Add to history
        entry = {
            "timestamp": utterance.started_at_s,
            "duration": utterance.ended_at_s - utterance.started_at_s,
            "speaker": user_id,
            "text": text,
        }
        self.conversation_history.append(entry)

        logger.info(f"[{user_id}] {text}")

    def get_speaker_turns(self) -> list[dict]:
        """
        Get conversation turns grouped by speaker.

        Returns:
            List of speaker turns with speaker changes
        """
        if not self.conversation_history:
            return []

        turns = []
        current_speaker = None
        current_turn = None

        for entry in self.conversation_history:
            if entry["speaker"] != current_speaker:
                # Speaker changed, start new turn
                if current_turn:
                    turns.append(current_turn)

                current_speaker = entry["speaker"]
                current_turn = {
                    "speaker": current_speaker,
                    "start_time": entry["timestamp"],
                    "utterances": [],
                }

            current_turn["utterances"].append(entry)
            current_turn["end_time"] = entry["timestamp"] + entry["duration"]

        # Add final turn
        if current_turn:
            turns.append(current_turn)

        return turns

    def get_speaker_statistics(self) -> dict:
        """
        Get statistics for each speaker.

        Returns:
            Dictionary of speaker statistics
        """
        stats = {}

        for entry in self.conversation_history:
            speaker = entry["speaker"]
            if speaker not in stats:
                stats[speaker] = {
                    "utterance_count": 0,
                    "total_duration": 0.0,
                    "word_count": 0,
                }

            stats[speaker]["utterance_count"] += 1
            stats[speaker]["total_duration"] += entry["duration"]
            stats[speaker]["word_count"] += len(entry["text"].split())

        return stats

    def export_transcript(self, output_file: str):
        """
        Export conversation transcript.

        Args:
            output_file: Output file path
        """
        with open(output_file, "w", encoding="utf-8") as f:
            f.write("# Conversation Transcript\n\n")

            for entry in self.conversation_history:
                timestamp = f"{entry['timestamp']:.2f}s"
                speaker = entry["speaker"]
                text = entry["text"]
                f.write(f"[{timestamp}] {speaker}: {text}\n")

            # Add statistics
            f.write("\n## Statistics\n\n")
            stats = self.get_speaker_statistics()
            for speaker, data in stats.items():
                f.write(f"### {speaker}\n")
                f.write(f"- Utterances: {data['utterance_count']}\n")
                f.write(f"- Total duration: {data['total_duration']:.2f}s\n")
                f.write(f"- Words: {data['word_count']}\n\n")

        logger.info(f"Transcript exported to {output_file}")

    def close(self):
        """Clean up resources."""
        self.voiceprint.close()


# Example usage
def example_integration():
    """Example of integrating speaker identification into Tank."""
    app_config = AppConfig()

    # Quick check: try creating a recognizer to see if speaker ID is available
    recognizer = create_voiceprint_recognizer(app_config)
    if not recognizer.enabled:
        print("⚠️  Speaker identification is disabled.")
        print("   Set ENABLE_SPEAKER_ID=true in .env to enable.")
        recognizer.close()
        return
    recognizer.close()

    print("=" * 60)
    print("Speaker Identification Integration Example")
    print("=" * 60)

    # Example 1: Speaker-aware perception
    print("\n1. Speaker-aware perception")
    perception = SpeakerAwarePerception(app_config)
    print("   ✓ Initialized")

    # Example 2: Personalized responses
    print("\n2. Personalized responses")
    response_gen = PersonalizedResponseGenerator()
    print(f"   Alice: {response_gen.generate_greeting('alice')}")
    print(f"   Bob: {response_gen.generate_greeting('bob')}")
    print(f"   Unknown: {response_gen.generate_greeting('Unknown')}")

    # Example 3: Enrollment workflow
    print("\n3. Speaker enrollment workflow")
    enrollment = SpeakerEnrollmentWorkflow(app_config)
    print("   ✓ Workflow initialized")
    print("   ℹ️  Use enrollment.enroll_speaker() to enroll new speakers")

    # Example 4: Conversation tracking
    print("\n4. Conversation tracking")
    tracker = ConversationTracker(app_config)
    print("   ✓ Tracker initialized")
    print("   ℹ️  Use tracker.add_utterance() to track conversations")

    # Cleanup
    perception.close()
    enrollment.close()
    tracker.close()

    print("\n" + "=" * 60)
    print("✅ Integration example complete!")
    print("=" * 60)


if __name__ == "__main__":
    example_integration()
