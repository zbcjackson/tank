import queue

# Global Queues
# 1. TextQueue: User input -> Brain
text_queue = queue.Queue()

# 2. AudioInputQueue: Mic -> Brain (Simulated audio data)
audio_input_queue = queue.Queue()

# 3. AudioOutputQueue: Brain -> Speaker (Text to be spoken, or audio chunks)
audio_output_queue = queue.Queue()

# 4. DisplayQueue: Brain/Others -> Main Thread (For strictly controlled printing)
display_queue = queue.Queue()
