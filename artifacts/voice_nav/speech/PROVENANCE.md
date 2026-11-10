# Speech fixtures

Generated on 2026-11-08 from three public Vietnamese demo sentences using Google
Translate TTS (`check_speech.py --engine google`), converted by ffmpeg to mono
16 kHz signed PCM16 WAV. These are synthesized voices, not recordings of a user.

- `command_1.wav`: Đi đến phòng học
- `command_2.wav`: Đi đến phòng thí nghiệm
- `command_3.wav`: Đi đến hành lang

Whisper and Vosk inference use local models. The application does not call
Google TTS; the optional fixture generator downloads these test samples only.
