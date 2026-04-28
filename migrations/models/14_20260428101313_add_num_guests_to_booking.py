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
    "start_date" DATE NOT NULL,
    "end_date" DATE NOT NULL,
    "status" VARCHAR(9) NOT NULL DEFAULT 'pending',
    "price_per_night" DECIMAL(8,2) NOT NULL,
    "total_price" DECIMAL(10,2) NOT NULL,
    "currency" VARCHAR(3) NOT NULL DEFAULT 'EUR',
    "num_guests" INT NOT NULL DEFAULT 1,
    "guest_name" VARCHAR(255),
    "guest_email" VARCHAR(255),
    "guest_phone" VARCHAR(50),
    "special_requests" TEXT,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON COLUMN "bookings"."status" IS 'PENDING: pending\nCONFIRMED: confirmed\nCOMPLETED: completed\nCANCELLED: cancelled\nNO_SHOW: no_show';
        DROP TABLE IF EXISTS "owner_stripe_accounts";
        DROP TABLE IF EXISTS "payments";"""


async def downgrade(db: BaseDBAsyncClient) -> str:
    return """
        DROP TABLE IF EXISTS "bookings";"""


MODELS_STATE = (
    "eJztme1vmzgYwP8VxKdO6lVpXrauOp2UpWzNKSFVS2/T7k6WAw6xCjYFszbq9X8/20AAB6"
    "KQLN2y7UsUnhds//zYz2PzpPvUQV508o7SO0xc/Vx70gn0Ef+jqo41HQZBrhACBqeetJ0m"
    "RlIIpxELoc24fAa9CHGRgyI7xAHDlHApiT1PCKnNDZNWU1FM8H2MAKMuYnMUcsXf/3IxJg"
    "56RFH2GNyBGUaeU+otdkTbUg7YIpCy29vhxXtpKZqbApt6sU9y62DB5pQszeMYOyfCR+hc"
    "RFAIGXIKwxC9TEeciZIecwELY7TsqpMLHDSDsSdg6L/PYmILBppsSfx0/9Ab4LEpEWgxYY"
    "LF03MyqnzMUqqLpgaX/eujzutXcpQ0Ym4olZKI/iwdIYOJq+Sag7RDJIYNIFsFesE1DPuo"
    "GmrZU4HrpK4n2Z9tIGeCnHIeYRnmDN92THU+BmdCvEU6g2sYW8OxcWP1x1diJH4U3XsSUd"
    "8yhKYtpQtFepRMCeXrI1k4y5doH4fWpSYetc8T01AnbmlnfdZFn2DMKCD0AUCnEGyZNAPD"
    "LfOJDUIaoJAtQLOlorh9zTWz/+ncZYlUkKMPfIDb8is6/4wU46gxu4LLz0gsYjBkQGyY1V"
    "txNbSy17pt+ODYiW1UYYSI05hQ0edH58OjgcXRKp3BHIYGiX1JaMgbgMRGVbGUeiuceIf2"
    "RUcP+PykFWcZkX5lmBdD88O5lpr8QwYT8/3wemxcnGsc0wyHPnKEdHw1MqxE6gceYlLaNw"
    "fGaCSlYrSeJ6TmBNxcTj5y2hREc547N6sTfPgIPERcNuePb9fMyV/9a7nk3yqZ30wVbaFR"
    "8w22EeBZAxDszqvqMGRjH3p1CWfFWw3yxP0kfc3hhbkxGI77o6Oz47aEyosszFARdrelMm"
    "WUQQ9INg15Kp4/KMvTVgOYdhyGiNiL6m2l5nRQ8HnBzcS4vd7hiFVe5p0Nlnmndpl3VIp8"
    "9wVujCJWsT0PCavGWHZSQPJu7wvk6Q4QXdHIb+3T7pvuWed194ybyI4sJW/WgB2alsJNDh"
    "/IpwbxV/baKgLTU9ZLHkdL8dfu9TaIQG5VG4NSV0UT+RB7zXEu3X7xLPMMOI0twnPpdpA8"
    "e60NcPZatTR7K4kmCnha5dk3RPc1G6WFHmt2yirfA8G67tbJ+GSVLpwyfEfj/qdXpUun0c"
    "T8kJkXcA9Gk3fq0TxwtrzzK3v+uvP7pnd+svPihnx2V7jaFYIptO8eYOiAFQ1t0zrbVZXf"
    "9lUJJNCVsyLYil6mnw36iBfMc73ig0KqOV73PQHmNt/N14TakqzygqqiFEsnbLevCDuG+l"
    "cpxeo/HnxBYSS61CDxFVxe7ljw3VcRYmk0gJiaHybA09YmdQO3qgUodcoRlRKGSEU++/Nm"
    "YtacUHMXNZFhm2n/aR6O9na+2lvBIMa7vmBQawMlDYkXiILhmyaW5/8BT9XddQ=="
)
