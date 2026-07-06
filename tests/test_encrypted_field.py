import pytest

from app.fields import EncryptedCharField


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
