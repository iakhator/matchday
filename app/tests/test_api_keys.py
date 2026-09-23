from app.core.api_keys import SECRET_PREFIX, generate_secret, hash_secret


class TestGenerateSecret:
    def test_plaintext_carries_the_identifiable_prefix(self):
        plaintext, _, _ = generate_secret()
        assert plaintext.startswith(SECRET_PREFIX)

    def test_prefix_is_a_short_slice_of_the_plaintext(self):
        plaintext, prefix, _ = generate_secret()
        assert plaintext.startswith(prefix)
        assert len(prefix) < len(plaintext)

    def test_hashed_matches_hash_secret_of_the_plaintext(self):
        plaintext, _, hashed = generate_secret()
        assert hashed == hash_secret(plaintext)

    def test_two_generated_secrets_never_collide(self):
        """Not a proof, but enough calls that a collision would mean the
        entropy source is broken, not that we got unlucky."""
        secrets_seen = {generate_secret()[0] for _ in range(1000)}
        assert len(secrets_seen) == 1000


class TestHashSecret:
    def test_deterministic(self):
        assert hash_secret("same-input") == hash_secret("same-input")

    def test_different_inputs_hash_differently(self):
        assert hash_secret("input-a") != hash_secret("input-b")

    def test_never_returns_the_plaintext(self):
        assert hash_secret("mk_live_something") != "mk_live_something"
