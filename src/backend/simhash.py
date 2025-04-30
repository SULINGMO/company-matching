import re
import hashlib

class Simhash:
    def __init__(self, text, weight_func=None, weights=None):
        self.value = self._simhash(text, weight_func, weights)

    def _tokenize(self, text):
        """
        Tokenize the input text and convert it to lowercase.
        Handles some common company-specific tokenization issues.
        """
        return re.findall(r'\w+', text.lower())

    def _hash(self, token):
        """
        Returns the MD5 hash of the token as a large integer.
        """
        return int(hashlib.md5(token.encode('utf-8')).hexdigest(), 16)

    def _simhash(self, text, weight_func, weights):
        """
        Generate the SimHash for the provided text using weighted tokens.
        """
        tokens = self._tokenize(text)
        v = [0] * 128  # SimHash vector for 128-bit hash

        for token in tokens:
            h = self._hash(token)
            category = weight_func(token) if weight_func else 'company'
            weight = weights.get(category, 1.0) if weights else 1.0

            for i in range(128):
                bitmask = 1 << i
                if h & bitmask:
                    v[i] += weight
                else:
                    v[i] -= weight

        fingerprint = 0
        for i in range(128):
            if v[i] >= 0:
                fingerprint |= 1 << i

        return fingerprint

def hamming_distance(hash1, hash2):
    """
    Calculate and return the Hamming distance between two hash values.
    """
    x = hash1 ^ hash2
    return bin(x).count('1')

def calculate_weighted_simhash(text1, text2, categorize_func, weights):
    """
    Compare two pieces of text by their weighted SimHash and return similarity ratio (0.0 to 1.0).
    """
    if not callable(categorize_func):
        raise TypeError("categorize_func must be a callable function")

    simhash1 = Simhash(text1, weight_func=categorize_func, weights=weights).value
    simhash2 = Simhash(text2, weight_func=categorize_func, weights=weights).value

    distance = hamming_distance(simhash1, simhash2)
    similarity = 1 - (distance / 128)

    return similarity

