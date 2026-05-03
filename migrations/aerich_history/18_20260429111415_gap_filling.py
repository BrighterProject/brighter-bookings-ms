from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """ 
    ALTER TABLE "bookings" ADD "gap_adjustment_pct" 
    DECIMAL(5,2) NOT NULL DEFAULT 0;"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """ALTER TABLE "bookings" DELETE COLUMN "gap_adjustment_pct" """


MODELS_STATE = (
    "eJztmW1vmzoUgP8K4lMn9VZpXrauupqUpWxlSkjV0m3admU54BBWsCmY20a9/e/XNhDAgS"
    "gkS7ts+xKF8wL242OfY/tB9YmNvOjoLSE3LnbUU+VBxdBH7I+sOlRUGAS5ggsonHjCdpIY"
    "CSGcRDSEFmXyKfQixEQ2iqzQDahLMJPi2PO4kFjMMPlqKoqxexsjQImD6AyFTPH1HyZ2sY"
    "3uUZQ9Bjdg6iLPLrXWtfm3hRzQeSBk19f62TthyT83ARbxYh/n1sGczghemMexax9xH65z"
    "EEYhpMgudIO3Mu1xJkpazAQ0jNGiqXYusNEUxh6Hof49jbHFGSjiS/yn+0ZtgMcimKN1Me"
    "UsHh6TXuV9FlKVf2pw3r886Lx8IXpJIuqEQimIqI/CEVKYuAquOUgrRLzbANJloGdMQ10f"
    "VUMte0pw7dT1KPuzCeRMkFPOIyzDnOHbjKnK+mCPsTdPR3AFY1MfaVdmf3TBe+JH0a0nEP"
    "VNjWvaQjqXpAfJkBA2P5KJs3iJ8kk3zxX+qHwZG5o8cAs784vK2wRjSgAmdwDahWDLpBkY"
    "ZpkPbBCSAIV0DppNFcntR86Z3Q/nNlOkghy5Yx3clF/R+XekGEeN2RVcfkdiEYUhBXzBrF"
    "6Kq6GVvVYtw3vHji+jEiOE7caEij6/Oh8WDTSOlukMZjDUcOwLQjr7AMQWqoql1FvixBq0"
    "KzpqwMYnrTjLiNQLzTjTjfenSmryDQ/Gxjv9cqSdnSoM09QNfWRz6ehiqJmJ1A88RIW0bw"
    "y04VBIeW89j0uNMbg6H39itAmIZix3rlcn+PAeeAg7dMYeX68Yk4/9SzHlX0uZ30gVba6R"
    "841rIcCyBsCuM6uqw5Dl+tCrSzhL3nKQJ+5H6Wv2L8y1gT7qDw9ODtsCKiuyXIqKsLstmS"
    "klFHpAsGnIU/L8RVketxrAtOIwRNiaVy8rNbuDgs8TLiba9eUWW6zyNO+sMc07tdO8I1Nk"
    "qy9wYhTRiuVZx7QaY9lJAsmavSuQx1tAdPhH/mofd191TzovuyfMRDRkIXm1AqxumBI30X"
    "0gnhrEX9lrowhMd1lPuR0txV+711sjAplVbQwKXRVN5EPXa45z4faHZ5lnwGhsEJ4Lt73k"
    "2WutgbPXqqXZW0o0CRWLxJiGjbLNkuNeAm2vE571wSnTjAJWpLBaJkS3NWnHRPc1eafKd0"
    "+YrjrD0z6bpeO7jN7BqP/5RekIbzg23mfmBdqD4fitHLQwAND+HkfUR5jNaatpBV/9gucp"
    "PFs7rTp7DYrOOLA3PJgue/45mH7Wg2nReH6NM70p3D9wwQRaN3cwtMGShrRJne2yym/7sg"
    "Ri6IhR4Wx5K9O7rT5iu7qZWnHrlWoOV116wdzmp7nyqt03VJ6iVuwX0gHb7qpry1D/IfuF"
    "+huuf1EY8SY1KCcKLk+3d/3pS10+NRpATM33E+Bxa53illnVAhQ66RyFYIpwRT77cDU2ao"
    "5Rchc5kbkWVf5TPDfa2SHAzuow3t/VdZhccklpiL+A12HPmlge/wdzu7mA"
)
