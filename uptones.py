from scipy.io import wavfile
from scipy.signal import resample

# Wczytaj plik dźwiękowy
fs, audio_data = wavfile.read('twoj_plik.wav')

# Przykładowe przesunięcie tonacji o pół tonu w górę
shift_ratio = 2**(1/12)  # stosunek przesunięcia o pół tonu w górę
shifted_audio_data = resample(audio_data, int(len(audio_data) / shift_ratio))

# Zapisz zmodyfikowany plik dźwiękowy
wavfile.write('zmodyfikowany_plik.wav', fs, shifted_audio_data.astype(audio_data.dtype))

