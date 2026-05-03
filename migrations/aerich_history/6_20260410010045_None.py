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
    "eJztmGtv2jwUx79KlFed1FUtsK2rpkmMZmsmCFWbbtMuikxiwKpjZ4nztKhPv/t8nIQkJr"
    "ACu7Tb3iD4n3Owz8+XY/vGDHmAabL3ivNLwibmkXFjMhRi+UU37RomiqLSAIJAI6p8R5mT"
    "EtEoETHyhdTHiCZYSgFO/JhEgnAmVZZSCiL3pWPWai6ljHxNsSf4BIspjqXh0xcpExbga5"
    "wUP6NLb0wwDWq9JQG0rXRPzCKlXVzYx6+VJzQ38nxO05CV3tFMTDmbu6cpCfYgBmwTzHCM"
    "BA4qaUAv84wLKeuxFESc4nlXg1II8BilFGCYL8Yp84GBoVqCj85Lcw08PmeAljABLG5us6"
    "zKnJVqQlO9k+7ZTvvpI5UlT8QkVkZFxLxVgUigLFRxLUH6MYa0PSQWgR5LiyAhboZaj9Tg"
    "BnnoXvFlE8iFUFIuZ1iBucC3GVNT5hAMGZ3lI7iCsWsPrHO3OziFTMIk+UoVoq5rgaWl1J"
    "mm7mRDwuX6yBbO/E+M97Z7YsBP4+PQsfSBm/u5H03oE0oF9xi/8lBQmWyFWoCRnuXARjGP"
    "cCxm3npLRQv7kWvm5w/nNkukgRy/kgluyq8a/DdSTJO12VVC/kZiiUCx8GDDbN6Km6HVo1"
    "Ztww+OHWyjGiPMgrUJVWP+dD5yNog0WaTTm6LYYmmoCNmyAcR83DSX8miNk+zQz6JjRnJ8"
    "8hNnHZF5ajnHtvPmyMhdPrPe0Hltnw2s4yNDYhqTOMQBqIPTvuVmahhRLJTadXpWv69UyJ"
    "ZSUJ2hd34yfC9pcy+Zytp5t3NCiK49itlETOXP5yvG5F33TC3551rld3JDCyx6vSE+9mTV"
    "8BiZTJvOYdgnIaLLCs5CtD7Js/C9/G8e3jS3evag29853G0pqPKQRQSuwu7s60wFF4h6is"
    "2aPLXIP5Tlwf4aMP00jjHzZ83bypLbQSXmF24m1sXZFles+jJv32GZt5cu87ZOkXGBG3Zm"
    "F1+LZoTzgI345XeE+zHtXOuDW7s3FZx2Bt0Pj2p3p/7QeVO4V7j2+sNX+gkzCja8utYj/1"
    "1df+vVVXUeHnrGl5UXChBGyL+8QnHgLVh4iy/zXTSFrVBXEEMTNSrAFnqZv351sdz3p2bD"
    "u1hu2V31LIZKn3vzKGazJbtL4z1LTi59tucDtt1j2JZTfQKtPG4ddJ51DttPO4fSRfVkrj"
    "xbMfttx/3OG9h/OE6gS2uUt0rIr6tuW1KsFbfWkyd3KG/Sa2mBU7b6jgxLYw2IufvDBHiw"
    "v38HgNJrKUBl005anAnMGurZ23N582k+aJUheiEjvjD+NyhJFhb1/QC6gh/ku/rAoJ8NtD"
    "IEfwAHht9aWG6/AUOhMIg="
)
