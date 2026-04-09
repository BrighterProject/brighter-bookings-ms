from tortoise import BaseDBAsyncClient

RUN_IN_TRANSACTION = True


async def upgrade(db: BaseDBAsyncClient) -> str:
    return """
        CREATE TABLE IF NOT EXISTS "bookings" (
    "id" UUID NOT NULL PRIMARY KEY,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "property_id" UUID NOT NULL,
    "property_owner_id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "start_datetime" TIMESTAMPTZ NOT NULL,
    "end_datetime" TIMESTAMPTZ NOT NULL,
    "status" VARCHAR(9) NOT NULL DEFAULT 'pending',
    "price_per_night" DECIMAL(8,2) NOT NULL,
    "total_price" DECIMAL(10,2) NOT NULL,
    "currency" VARCHAR(3) NOT NULL DEFAULT 'EUR',
    "notes" TEXT,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON COLUMN "bookings"."status" IS 'PENDING: pending\nCONFIRMED: confirmed\nCOMPLETED: completed\nCANCELLED: cancelled\nNO_SHOW: no_show';
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        """


MODELS_STATE = (
    "eJztWG1v2jAQ/itRPnVSV1Fg64umSQyyNROEqk23qtsUmcSAVcdOE2ct6vrfZzsJSUxgBb"
    "a2tPuCyHN3se+5N8e3uk89iKOdD5ReIjLSD7VbnQAf8j+qaFvTQRDkAgEwMMBSd5AoSRAM"
    "IhYCl3F8CHAEOeTByA1RwBAlHCUxxgKkLldMVk2hmKCrGDqMjiAbw5ALvv3gMCIevIFR9h"
    "hcOkMEsVfaLfLE2hJ32CSQ2NmZ2fkoNcVyA8elOPZJrh1M2JiSqXocI29H2AjZCBIYAga9"
    "ghtil6nHGZTsmAMsjOF0q14OeHAIYizI0N8NY+IKDjS5kvhpvteXoMelRFCLCBNc3N4lXu"
    "U+S1QXS7WPWidbjbevpJc0YqNQCiUj+p00BAwkppLXnEg3hMJtB7BZQjtcwpAPq0ktWyrk"
    "eqnpTvZnFZIzIGc5z7CM5oy+1TjVuQ9en+BJGsEFHNtmzzi1W71j4YkfRVdYUtSyDSGpS3"
    "SioFtJSCivj6Rwpi/Rvpr2kSYetYu+ZaiBm+rZF7rYE4gZdQi9doBXSLYMzYjhmnlgg5AG"
    "MGQTZ7lSUcz+Zs38+3CuUyIVzNFr7uCq/BWNXyKLcbQ0dwWTl8hYxEDInGLDXKYdz1pvZk"
    "vekBacub2wB0PirRxP1fZ/NB87mrzCWBzNxrE9BqFBYl/G0eTuA+LCqvpMrZVIcrr+Vez0"
    "gGdRepovB1A/NqyOaX061FKV76Tdtz6aJz2jc6jxIA5R6ENPoL3jrmEnqB9gyCTastpGty"
    "tR4S3GArX6zulR/yvPBepEY87i/c5gPrhxMCQjNuaPBwsy5kvrRLbTAyUJrFRQFxJ1liMX"
    "OnwiOwSNxlVnXOgiH+B5w3zGWi3DxHwnfc3GFWHHaJu9Vndrf7suSeX1hhgskt2sqZwyyg"
    "B2JDdL8qlYPlMud2tLkOnGYQiJO6luK3O+vAo2D9hMjLOTNT5fy2XeuEeZN+aWeUNlkVAG"
    "KzqzDW9YNYVTg5X4S7+/nkba2ca5XRqhGU9bvdb5q9IY7fatT5l6gdd2t/9BPb0H3orXAm"
    "XLzTy1PJtrAbl5cYk2vCzc/ghgANzLaxB6zoyE1uk83VmRX/dVBBAwklER3IpdpjeLLcj7"
    "/livuHNMJduLrhxBrvNkLhxNMqe7VH7D8uRSsz0N2HoXjWum+kis8rq+29xr7jfeNve5it"
    "zJFNlbkP2mZf/hfvEnDCOxpSXGW8Hk4abbmiyWhlv9zZt7jDeuNXfASVm5I4vSWILEVH0z"
    "Cdyt1e5BINeaS6CUKSctShgkFfPs8yn/8qk+aOUm6iBDLtN+aRhFM0X9NAhdwJ/wd/GBQT"
    "0bKGNIvEAcGB51sNz9BpJsmrY="
)
