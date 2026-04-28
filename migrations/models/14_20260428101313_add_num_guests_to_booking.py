from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "bookings" ADD "num_guests" INT NOT NULL DEFAULT 1;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "bookings" DROP COLUMN "num_guests";"""


MODELS_STATE = (
    "eJztmW1P4zgQgP9KlE+sxCHoCwvodFJpc0tPbYog3K72bmW5iZtaJHZwnINqj/9+tvPatG"
    "m7oUEHd19KM+POjB+Px/HwXfepg7zwqIcYtuf6hfZdh0Eg/iYK/VDTCfRRLkmHCgWHU09p"
    "YCbCxEFPKBTCP76JRx8S6CJHPJLI84QATkPOoM2FZAa9EAlRcA9mGHmOcp76wo60FhH8EM"
    "lnziI51EEzGHk8Nxe7c/IRUp5Eldp3psCmXuST3K5DbREGJm5uyUUEMciLtlRUgC8CFdGQ"
    "8F9VmEJjUyKngQkPVdSuHPFT66TzsXPWPu2ciSEqhEzy8VlFH9oMBxxTkvsNFnxOSeZFmN"
    "TjmHPvsQ8Vg2npz8/rJzBLMObsW35JQlu0JHEghwVRzv8vxEIZZ3ERMqDVq5AO2bYMBfNb"
    "1iL9+fJi9OeQVa6GD5+Ah4jLZT63ut1d2QsjG9j/3rvpX/VuDoTBD3IYFWkcZ7+ZqFqxTi"
    "5QDlLupoYgJqYbBnhyfLxfgMJgJUClWwYoguMo3hVNQCyYrwXyt9uJWQVyV24Otrn2t+bh"
    "cNPml56k2g/DB6+I7WDc+1Im2h9NLqUooCF3mbKiDFwKut+qwor5Ak5dxOeIpUViCu37R8"
    "gcsFJiMk2pssiJJ6fFJaX3MdLtJ0s6tni0TGNZ+JqHi/7zLCK2ZKNFEXaO5EfnF/2wqfNm"
    "fWbd3Q0HL80sFb40tCGvVAq1Tz+U00X97HVOG5shiQLA2tscRpwCQh9/ZOcvOa21RAOh5d"
    "hHlZVUuHAmxFskCbNzQUjsHqVf9MIUAXQKCVixqNZwbNxavfH1UsUY9CxDalpKuihJD05L"
    "VSQzon0eWleafNS+TkyjnCnZOOtrqXgHjAaI8QUobbk9FvCSi7e91daQo48i+tfgV3T0Xi"
    "hGYaPsCubfC7GQQ8aBrDtNQVv2ULvuvvilq1hjN7CT1bHECBGnUUJF+2+Rj1hhHoVb6OiB"
    "mGbytlcriRIXta8/Bol8BWko+EBio61XofNVdvq1YQ6G5qcLLZnOn6QvLgTDm7ExuNCEtR"
    "lmPnKkdHw9MqxY6gce4kraM/vGaKSkMgTPk1JzAm6vJp/FfCgI5+KlZnV1drtqnVdetM7L"
    "16yAYRsBcRIAgt15Y9etNW7qZTiysQ+9Fyd5bOYoMbcpzY3+cNwbHZwdthRU8e6EOSrC7q"
    "xcXTnl0ANqyk3xLLl4WyxPjn8Aph0xhoi92FZWjLubeiWl6KDhnkp7vx2VduU2b5cpipoH"
    "3AiFfFt5PqnFcNl8LYr/pj5rzk1NCqinl+/k/OqWk1t28M6bovFkkQ+x1yjOzMN/gmcg/D"
    "SbnpmHhnl299xy7lZ3nLsrB00YiANMHKoMPexSKOsSXeemFlYLPVVWzP1gtIwv1ubOc9ZL"
    "Gk3MT+nwcju6dDUPnP31/Hbsxi77/L/lt6+W3yv8R+H5H5gv3XU="
)
