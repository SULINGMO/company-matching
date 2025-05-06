import re
import hashlib
import numpy as np

class Simhash:
    def __init__(self, text, weight_func=None, weights=None, hashbits=128):
        self.hashbits = hashbits
        self.value = self._simhash(text, weight_func, weights)

    def _tokenize(self, text):
      if not isinstance(text, str):
        text = str(text) if text is not None else ""
        return re.findall(r'\w+', text.lower())


    def _hash_bin(self, token):
        """
        Returns a binary string of the hash of the token.
        """
        return bin(int(hashlib.md5(token.encode('utf-8')).hexdigest(), 16))[2:].zfill(self.hashbits)

    def _simhash(self, text, weight_func, weights):
        tokens = self._tokenize(text)
        if not tokens:
            return 0

        v = np.zeros(self.hashbits, dtype=np.float32)

        for token in tokens:
            weight = 1.0
            if weight_func:
                category = weight_func(token)
                weight = weights.get(category, 1.0) if weights else 1.0

            hashbits = self._hash_bin(token)
            for i, bit in enumerate(hashbits):
                v[i] += weight if bit == '1' else -weight

        # Generate final fingerprint
        fingerprint = 0
        for i, val in enumerate(v):
            if val >= 0:
                fingerprint |= (1 << (self.hashbits - 1 - i))

        return fingerprint


def hamming_distance(hash1, hash2):
    return bin(hash1 ^ hash2).count('1')

def calculate_weighted_simhash(text1, text2, categorize_func, weights):
    if not callable(categorize_func):
        raise TypeError("categorize_func must be a callable function")

    simhash1 = Simhash(text1, weight_func=categorize_func, weights=weights).value
    simhash2 = Simhash(text2, weight_func=categorize_func, weights=weights).value

    distance = hamming_distance(simhash1, simhash2)
    similarity = 1 - (distance / 128)
    return similarity
