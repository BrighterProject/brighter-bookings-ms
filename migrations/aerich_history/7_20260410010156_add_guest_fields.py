from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "bookings" ADD "guest_email" VARCHAR(255);
        ALTER TABLE "bookings" ADD "guest_name" VARCHAR(255);
        ALTER TABLE "bookings" ADD "special_requests" TEXT;
        ALTER TABLE "bookings" ADD "guest_phone" VARCHAR(50);
        ALTER TABLE "bookings" DROP COLUMN "notes";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        ALTER TABLE "bookings" ADD "notes" TEXT;
        ALTER TABLE "bookings" DROP COLUMN "guest_email";
        ALTER TABLE "bookings" DROP COLUMN "guest_name";
        ALTER TABLE "bookings" DROP COLUMN "special_requests";
        ALTER TABLE "bookings" DROP COLUMN "guest_phone";"""


MODELS_STATE = (
    "eJztmG1v2zYQx7+KoFcpkAWOH9o0GAa4jtposOUgUdai2yDQEi0ToUhFopoYWb77SEqyJF"
    "ryLGdN47Zvguh/dyb549PxHvSAehDHR+8ovUHE10+1B52AAPJ/VNOhpoMwLAxCYGCGpe8s"
    "dZIimMUsAi7j+hzgGHLJg7EboZAhSrhKEoyFSF3umLaaSQlBtwl0GPUhW8CIG/78m8uIeP"
    "AexvlneOPMEcRepbfIE21L3WHLUGrX1+bZe+kpmps5LsVJQArvcMkWlKzckwR5RyJG2HxI"
    "YAQY9ErDEL3MRpxLaY+5wKIErrrqFYIH5yDBAob+6zwhrmCgyZbEn/5vegs8LiUCLSJMsH"
    "h4TEdVjFmqumhqdD68POi9fiVHSWPmR9IoieiPMhAwkIZKrgVIN4Ji2A5g60DPuIWhANZD"
    "rUYqcL0s9Cj/ZxfIuVBQLlZYjjnHtxtTnY/BmxK8zGZwA2PbnBhX9nByIUYSxPEtloiGti"
    "EsXakuFfUgnRLK90e6cVY/on007XNNfGqfp5ahTtzKz/6siz6BhFGH0DsHeKXFlqs5GO5Z"
    "TGwY0RBGbOm02ypK2P+5Z77+dD5li9SQo3d8gLvyKwf/iBSTuDW7UsiPSCxmIGKOODDrj+"
    "J6aNWoTcfw3rETx6jCCBKvNaFyzPfOh68GlsTrdEYLEBkkCSQhkzcAiAvr1lIWrXDiHfpa"
    "dPSQz0+WcVYR6ReGdWZaH061zOUvMppa783LiXF2qnFMcxQF0BPq5GJs2KkahBgyqQ6tkT"
    "EeS1WMFmOhWlPn6nz6kdOmTrzgd+d2eUIA7h0Mic8W/PPthjn5Y3gpt/xb5ea3MkNXWNT7"
    "BrnQ4beGQ5C/qMvDoIsCgJsunLVodZGn4UfZz+zfMjdG5mQ4Pjg57EqoPMlCDJZh9zsqU0"
    "YZwI5k05KnEvmdsjzutIDpJlEEibusP1YaXgelmGc8TIzryyc8sarbvLfFNu81bvOeStFP"
    "YMwc+dWCYzVqJ5LZa+E5n1UVjt3BYAuS3KuRpbTV0YQBQLg9zlXYT55VniGnscPyXIXtJc"
    "9BZwucg04jzcHagRmH/Hrgt0gEbwWfmnzMhvesIZ+vid0TrJuqJ8Ynu1I4yfEdTIafXlWK"
    "J+Op9SF3L+Eejafv1Cdm6O1Yu6pG/qxdfdPaley8qPTOb0olSiHMgHtzByLPWbPQLm3yXT"
    "cF3UBVAAG+nBXBVvQyK38PIU/8FnpNYTyzHG6qi4PC58VUxU3ScNDUFlr44lJXezZhT6uG"
    "P3Gp+6KVX7rH/Tf9k97r/gl3kT1ZKW82rH7Tsv+jCP4FRrHoUouLrxTyfOnti88ixNZoAT"
    "Fz30+Ax51t8gbu1QhQ2pSnFiUMkpr77PerqdXw0ipC1IsMuUz7R8MoXtvULwPoBn5ivJsT"
    "BjU3UK4h8QMiYfimF8vjv2npeyE="
)
