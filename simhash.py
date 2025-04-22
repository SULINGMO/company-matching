import re
import hashlib

class Simhash:
    def __init__(self, text, weight_func=None, weights=None):
        self.value = self._simhash(text, weight_func, weights)

    def _tokenize(self, text):
        return re.findall(r'\w+', text.lower())

    def _hash(self, token):
        return int(hashlib.md5(token.encode('utf-8')).hexdigest(), 16)

    def _simhash(self, text, weight_func, weights):
        tokens = self._tokenize(text)
        v = [0] * 128

        for token in tokens:
            h = self._hash(token)
            category = weight_func(token) if weight_func else 'company'
            weight = weights.get(category, 1.0) if weights else 1.0

            for i in range(128):
                bitmask = 1 << i
                v[i] += weight if h & bitmask else -weight

        fingerprint = 0
        for i in range(128):
            if v[i] >= 0:
                fingerprint |= 1 << i
        return fingerprint

def calculate_weighted_simhash(text, categorize_func, weights):
    simhash = Simhash(text, weight_func=categorize_func, weights=weights)
    return simhash.value
