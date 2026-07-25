#!/usr/bin/env python3
"""Generate a simple ringtone WAV file."""
import struct, math, wave

RINGTONE_PATH = '/home/raspberry/ringtone.wav'
SAMPLE_RATE = 44100
DURATION = 1.0  # 1 second, will loop

# North American ring tone: 440Hz + 480Hz, 2s on / 4s off
# For a simple ringtone, we'll do 2 seconds of tone
TONE_FREQS = [440, 480]
TONE_DURATION = 2.0

samples = []
n_samples = int(SAMPLE_RATE * TONE_DURATION)
for i in range(n_samples):
    t = i / SAMPLE_RATE
    val = 0
    for freq in TONE_FREQS:
        val += math.sin(2 * math.pi * freq * t)
    val = val / len(TONE_FREQS) * 0.3  # Normalize and reduce volume
    samples.append(val)

with wave.open(RINGTONE_PATH, 'w') as w:
    w.setnchannels(1)
    w.setsampwidth(2)
    w.setframerate(SAMPLE_RATE)
    for s in samples:
        w.writeframes(struct.pack('<h', int(s * 32767)))

print(f'Generated ringtone: {RINGTONE_PATH} ({TONE_DURATION}s)')
