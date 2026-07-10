import pytest

from app.fields import EncryptedCharField, _looks_like_fernet_token


def test_round_trip_encrypt_decrypt():
    field = EncryptedCharField(max_length=512)
    ciphertext = field.to_db_value("1234567890", instance=None)
    assert ciphertext != "1234567890"
    assert field.to_python_value(ciphertext) == "1234567890"


def test_different_plaintexts_produce_different_ciphertexts():
    field = EncryptedCharField(max_length=512)
    a = field.to_db_value("1111111111", instance=None)
    b = field.to_db_value("2222222222", instance=None)
    assert a != b


def test_tampered_ciphertext_raises():
    field = EncryptedCharField(max_length=512)
    ciphertext = field.to_db_value("1234567890", instance=None)
    tampered = ciphertext[:-4] + "abcd"
    with pytest.raises(ValueError):
        field.to_python_value(tampered)


def test_none_passes_through_untouched():
    field = EncryptedCharField(max_length=512)
    assert field.to_db_value(None, instance=None) is None
    assert field.to_python_value(None) is None


def test_missing_key_raises(monkeypatch):
    import app.fields as fields_module

    fields_module._get_fernet.cache_clear()
    monkeypatch.setattr("app.settings.booking_field_encryption_key", "")
    with pytest.raises(RuntimeError):
        fields_module._get_fernet()
    fields_module._get_fernet.cache_clear()


def test_short_value_with_fernet_version_byte_is_not_sniffed_as_token():
    # "gAEC" decodes to bytes starting with 0x80 (the Fernet version marker)
    # but is far shorter than a real token (min 100 chars) -- must not be
    # mistaken for ciphertext.
    assert _looks_like_fernet_token("gAEC") is False


def test_plaintext_resembling_short_token_passes_through_untouched():
    field = EncryptedCharField(max_length=512)
    assert field.to_python_value("gAEC") == "gAEC"


def test_key_rotation_decrypts_with_old_key(monkeypatch):
    from cryptography.fernet import Fernet

    import app.fields as fields_module

    old_key = Fernet.generate_key().decode()
    new_key = Fernet.generate_key().decode()

    fields_module._get_fernet.cache_clear()
    monkeypatch.setattr("app.settings.booking_field_encryption_key", old_key)
    field = EncryptedCharField(max_length=512)
    ciphertext = field.to_db_value("1234567890", instance=None)

    fields_module._get_fernet.cache_clear()
    monkeypatch.setattr(
        "app.settings.booking_field_encryption_key", f"{new_key},{old_key}"
    )
    assert field.to_python_value(ciphertext) == "1234567890"

    new_ciphertext = field.to_db_value("0987654321", instance=None)
    assert field.to_python_value(new_ciphertext) == "0987654321"

    fields_module._get_fernet.cache_clear()
