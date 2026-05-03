from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "bookings" ADD "guest_country" VARCHAR(2);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "bookings" DROP COLUMN "guest_country";"""


MODELS_STATE = (
    "eJztme1vmzgYwP8VxKdO6lVpXrauOp2UpWzNKSFVS2/T7k7IAYdYBZsaszbq9X8/20AAB6"
    "KQLN2y7UtVnpfY/vmxn8f2kx4QF/rRyTtC7hD29HPtSccggPwfVXWs6SAMc4UQMDD1pe00"
    "MZJCMI0YBQ7j8hnwI8hFLowcikKGCOZSHPu+EBKHGyatpqIYo/sY2ox4kM0h5Yq//+VihF"
    "34CKPsM7yzZwj6bqm3yBVtS7nNFqGU3d4OL95LS9Hc1HaIHwc4tw4XbE7w0jyOkXsifITO"
    "gxhSwKBbGIboZTriTJT0mAsYjeGyq24ucOEMxL6Aof8+i7EjGGiyJfGn+4feAI9DsECLMB"
    "Msnp6TUeVjllJdNDW47F8fdV6/kqMkEfOoVEoi+rN0BAwkrpJrDtKhUAzbBmwV6AXXMBTA"
    "aqhlTwWum7qeZP9sAzkT5JTzCMswZ/i2Y6rzMbgT7C/SGVzD2BqOjRurP74SIwmi6N6XiP"
    "qWITRtKV0o0qNkSghfH8nCWf6I9nFoXWriU/s8MQ114pZ21mdd9AnEjNiYPNjALQRbJs3A"
    "cMt8YkNKQkjZwm62VBS3r7lm9j+duyyRCnLkgQ9wW35F55+RYhw1Zldw+RmJRQxQZosNs3"
    "orroZW9lq3DR8cO7GNKowgdhsTKvr86Hx4NLA4WqUzmANq4DiQhIa8AYAdWBVLqbfCiXdo"
    "X3T0kM9PWnGWEelXhnkxND+ca6nJP3gwMd8Pr8fGxbnGMc0QDaArpOOrkWEl0iD0IZPSvj"
    "kwRiMpFaP1fSE1J/bN5eQjp03saM5z52Z1QgAebR9ij83559s1c/JX/1ou+bdK5jdTRVto"
    "1HyDHGjzrGFj5M2r6jDooAD4dQlnxVsN8sT9JP2ZwwtzYzAc90dHZ8dtCZUXWYjBIuxuS2"
    "XKCAO+Ldk05Kl4/qAsT1sNYDoxpRA7i+ptpeZ0UPB5wc3EuL3e4YhVXuadDZZ5p3aZd1SK"
    "fPe1vRhGrGJ7HmJWjbHspIDk3d4XyNMdIHqikd/ap9033bPO6+4ZN5EdWUrerAE7NC2Fmx"
    "y+Lb8axF/Za6sITE9ZL3kcLcVfu9fbIAK5VW0MSl0VTRgA5DfHuXT7xbPMM+Q0tgjPpdtB"
    "8uy1NsDZa9XS7K0kmoSKQ2LMaKNss+J4kEDbm4RnfXCqNKOQFym8lqHwvibtWPCxJu9U+R"
    "4I03V3eMYnq3R9l9E7Gvc/vSpd4Y0m5ofMvEB7MJq8Uy86QnfLG9Sy568b1G96gyo7L94b"
    "ZneFi3IhmALn7gFQ117RkDaps11VBe1AlQAMPDkrgq3oZfoI04f8+DHXK55nUs3xutcZkN"
    "t8N28ztQVu5XVfRWGbTthubzI7hvpXKWzrn2K+QBqJLjXIewWXlztkffc1mVgaDSCm5ocJ"
    "8LS1SRXGrWoBSp1y4CeYQVyRz/68mZg15/3cRU1kyGHaf5qPor2dVvdWMIjxri8Y1NpASU"
    "PiB0TB8E0Ty/P/VKlJ7w=="
)
