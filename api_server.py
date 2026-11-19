import json
import os
import re
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

ROOT = Path(__file__).resolve().parent
ENV_FILE = Path.home() / ".config" / "rende-capital" / ".env"
API_URL = "https://api.etherscan.io/v2/api"

def load_api_key():
    key = os.environ.get("ETHERSCAN_API_KEY", "").strip()
    if key:
        return key
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            if line.startswith("ETHERSCAN_API_KEY="):
                key = line.split("=", 1)[1].strip()
                if key and key != "COLE_SUA_CHAVE_AQUI":
                    return key
    raise RuntimeError("Chave da API não configurada no servidor.")

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        origin = self.headers.get("Origin", "")
        permitidas = ("https://rendecapital.xyz", "https://www.rendecapital.xyz", "http://127.0.0.1:8080")
        if origin in permitidas:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if urlparse(self.path).path != "/api/portfolio":
            return super().do_GET()

        address = parse_qs(urlparse(self.path).query).get("address", [""])[0].strip()
        if not re.fullmatch(r"0x[a-fA-F0-9]{40}", address):
            self.send_json({"ok": False, "error": "Endereço de carteira inválido."}, 400)
            return

        try:
            key = load_api_key()
            results = {}

            requests = {
                "balance": {
                    "module": "account",
                    "action": "balance",
                    "address": address,
                    "tag": "latest"
                },
                "transactions": {
                    "module": "account",
                    "action": "txlist",
                    "address": address,
                    "startblock": "0",
                    "endblock": "99999999",
                    "page": "1",
                    "offset": "100",
                    "sort": "desc"
                },
                "token_transfers": {
                    "module": "account",
                    "action": "tokentx",
                    "address": address,
                    "startblock": "0",
                    "endblock": "99999999",
                    "page": "1",
                    "offset": "100",
                    "sort": "desc"
                }
            }

            requests["weth_balance"] = {
                "module": "account",
                "action": "tokenbalance",
                "contractaddress": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
                "address": address,
                "tag": "latest"
            }
            requests["usdt_balance"] = {
                "module": "account",
                "action": "tokenbalance",
                "contractaddress": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
                "address": address,
                "tag": "latest"
            }

            for name, params in requests.items():
                params.update({"chainid": "1", "apikey": key})
                query = "&".join(
                    f"{k}={__import__('urllib.parse').parse.quote(str(v))}"
                    for k, v in params.items()
                )
                req = Request(API_URL + "?" + query,
                              headers={"User-Agent": "RendeCapital/1.0"})
                with urlopen(req, timeout=25) as response:
                    results[name] = json.loads(response.read().decode())

            try:
                price_url = "https://api.coingecko.com/api/v3/simple/price?ids=ethereum,tether&vs_currencies=brl"
                with urlopen(price_url, timeout=20) as response:
                    prices = json.loads(response.read().decode())
                results["prices"] = {
                    "eth_brl": prices["ethereum"]["brl"],
                    "weth_brl": prices["ethereum"]["brl"],
                    "usdt_brl": prices["tether"]["brl"]
                }
            except Exception as price_error:
                results["prices"] = {"error": str(price_error)}

            self.send_json({
                "ok": True,
                "address": address,
                "network": "Ethereum Mainnet",
                "data": results
            })

        except Exception as exc:
            self.send_json({
                "ok": False,
                "error": str(exc)
            }, 502)

if __name__ == "__main__":
    print("RENDE CAPITAL: servidor iniciado em http://127.0.0.1:8081")
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", "8082"))), Handler).serve_forever()
