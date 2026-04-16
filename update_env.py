import sys

env_path = "/srv/salomao/dev/app/backend/.env"
with open(env_path, "r") as f:
    text = f.read()

text = text.replace(
    "PUBLIC_ORIGIN=https://dev.raquel-talita.vps-kinghost.net",
    "PUBLIC_ORIGIN=https://salomao-vps.tail2033b8.ts.net"
)

with open(env_path, "w") as f:
    f.write(text)
print("Updated .env file successfully.")
