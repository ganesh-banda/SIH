"""Exercise the real frontend and backend in a headless Chromium DevTools tab.

Start FastAPI on 127.0.0.1:8000 and the static server on 127.0.0.1:5173.
Then launch Edge or Chrome with --headless=new --remote-debugging-port=9222
and run this script with the backend virtual environment (websockets is installed).
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import urllib.request
from pathlib import Path

import websockets

FRONTEND = "http://127.0.0.1:5173/"
OUTPUT = Path(__file__).parent / ".browser-results"


class Browser:
    def __init__(self, connection):
        self.connection = connection
        self.next_id = 0
        self.exceptions = []
        self.console_errors = []

    async def call(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        request_id = self.next_id
        await self.connection.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            message = json.loads(await self.connection.recv())
            if message.get("method") == "Runtime.exceptionThrown":
                self.exceptions.append(message["params"]["exceptionDetails"])
            if message.get("method") == "Runtime.consoleAPICalled" and message["params"].get("type") == "error":
                self.console_errors.append(message["params"])
            if message.get("method") == "Log.entryAdded" and message["params"]["entry"].get("level") == "error":
                self.console_errors.append(message["params"]["entry"])
            if message.get("id") == request_id:
                if "error" in message:
                    raise AssertionError(f"{method}: {message['error']}")
                return message["result"]

    async def evaluate(self, expression: str):
        result = await self.call("Runtime.evaluate", {
            "expression": expression, "awaitPromise": True, "returnByValue": True
        })
        if "exceptionDetails" in result:
            raise AssertionError(result["exceptionDetails"].get("text", expression))
        return result["result"].get("value")

    async def wait_for(self, condition: str, label: str):
        expression = """(async () => {
          for (let i=0;i<100;i++) {
            if (%s) return true;
            await new Promise(resolve => setTimeout(resolve, 100));
          }
          return false;
        })()""" % condition
        assert await self.evaluate(expression), f"Timed out: {label}"

    async def screenshot(self, name: str):
        OUTPUT.mkdir(exist_ok=True)
        result = await self.call("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False})
        (OUTPUT / name).write_bytes(base64.b64decode(result["data"]))


async def run(port: int):
    targets = json.load(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=5))
    page = next(item for item in targets if item["type"] == "page")
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=16 * 1024 * 1024) as socket:
        browser = Browser(socket)
        await browser.call("Page.enable")
        await browser.call("Runtime.enable")
        await browser.call("Log.enable")
        await browser.call("Emulation.setDeviceMetricsOverride", {
            "width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False
        })
        await browser.call("Page.navigate", {"url": FRONTEND})
        await browser.wait_for('document.querySelector("#connection")?.classList.contains("online")', "API connection")
        await browser.wait_for('document.querySelectorAll("#alertList tr[data-alert]").length > 0', "ranked alerts")
        assert await browser.evaluate('document.querySelector("#metricTransactions").textContent') != "—"
        await browser.screenshot("desktop-hero.png")
        print("PASS dashboard, real API connection, ranked alerts")

        await browser.evaluate('document.querySelector("#featuredButton").click()')
        await browser.wait_for('!document.querySelector("#caseContent").hidden', "featured case")
        await browser.wait_for('document.querySelectorAll("#graphViewport .graph-node-click").length > 1', "graph nodes")
        await browser.wait_for('document.querySelector("#networkContext").textContent.includes("Observed source IP")', "network observation")
        assert await browser.evaluate('document.querySelectorAll("#transactionList [data-tx]").length') > 0
        assert await browser.evaluate('document.querySelector("#caseExplanation").textContent.length') > 20
        assert await browser.evaluate('document.querySelectorAll("#shapList .shap-row").length') > 0
        await browser.evaluate('window.scrollTo({top: document.querySelector("#caseContent").getBoundingClientRect().top + scrollY - 95, behavior: "instant"})')
        await browser.evaluate('new Promise(resolve => setTimeout(resolve, 150))')
        await browser.screenshot("desktop-workspace.png")
        print("PASS featured alert, risk, backend explanation, history, SHAP, graph, network")

        original_wallet = await browser.evaluate('document.querySelector("#copyAddress").textContent.trim().split(" ")[0]')
        txid = await browser.evaluate('document.querySelector("#transactionList [data-tx]").dataset.tx')
        await browser.evaluate('document.querySelector("#zoomIn").click()')
        assert await browser.evaluate('document.querySelector("#graphViewport").getAttribute("transform").includes("1.2")')
        await browser.evaluate('document.querySelector("#zoomReset").click()')
        await browser.evaluate("""document.querySelector('#graphViewport [data-node^="tx:"]').dispatchEvent(new MouseEvent("click", {bubbles:true}))""")
        await browser.wait_for('!document.querySelector("#transactionDetail").hidden', "graph node selection")
        await browser.evaluate('document.querySelector("#closeTransaction").click()')
        await browser.evaluate("""document.querySelector('#graphViewport [data-node^="tx:"]').dispatchEvent(new KeyboardEvent("keydown", {key:"Enter",bubbles:true}))""")
        await browser.wait_for('!document.querySelector("#transactionDetail").hidden', "keyboard graph node selection")
        print("PASS interactive graph zoom")

        await browser.evaluate("""(() => {
          const field=document.querySelector("#lookupInput");
          field.value=%s;
          document.querySelector("#lookupForm").requestSubmit();
        })()""" % json.dumps(original_wallet))
        await browser.wait_for('document.querySelector("#lookupMessage").textContent === "Address found."', "address lookup")
        await browser.evaluate("""(() => {
          const field=document.querySelector("#lookupInput");
          field.value=%s;
          document.querySelector("#lookupForm").requestSubmit();
        })()""" % json.dumps(txid))
        await browser.wait_for('!document.querySelector("#txStandalone").hidden && document.querySelector("#standaloneTransactionContent").textContent.includes("TOTAL OUTPUT")', "TXID lookup")
        print("PASS direct address and TXID lookup")

        await browser.evaluate("""(() => {
          document.querySelector("#lookupInput").value="bc1qnotarealaddress123456789";
          document.querySelector("#lookupForm").requestSubmit();
        })()""")
        await browser.wait_for('document.querySelector("#lookupMessage").textContent.includes("not found")', "invalid address")
        print("PASS not-found handling")

        await browser.evaluate('document.querySelector("#tabAlerts").click()')
        await browser.evaluate('document.querySelector("[data-filter=patterns]").click()')
        await browser.wait_for('document.querySelectorAll("#alertList tr[data-alert]").length > 0', "pattern filter")
        assert await browser.evaluate('!document.querySelector("#alertsView").hidden')
        await browser.evaluate("""(() => {
          const sort=document.querySelector("#sortAlerts");
          sort.value="anomaly_desc";
          sort.dispatchEvent(new Event("change", {bubbles:true}));
        })()""")
        await browser.wait_for('document.querySelector("#queuePageLabel").textContent.includes("anomaly score")', "server-backed sorting")
        first_sorted = await browser.evaluate('document.querySelector("#alertList tr[data-alert]").dataset.alert')
        expected_sorted = await browser.evaluate("""(async () => {
          const response=await fetch("http://127.0.0.1:8000/alerts?limit=1&has_pattern=true&sort=anomaly_desc");
          return (await response.json())[0].alert_id;
        })()""")
        assert first_sorted == expected_sorted, "Sorting did not match backend order"
        await browser.evaluate("""(() => {
          document.querySelector("[data-filter=all]").click();
          const field=document.querySelector("#searchInput");
          field.value=%s;
          field.dispatchEvent(new Event("input", {bubbles:true}));
        })()""" % json.dumps(original_wallet))
        await browser.wait_for('document.querySelectorAll("#alertList tr[data-alert]").length === 1', "address filter")
        print("PASS tabs, pattern filter, and address search")

        await browser.evaluate("""(() => {
          document.querySelector("#settingsButton").click();
          document.querySelector("#apiUrl").value="http://127.0.0.1:8999";
          document.querySelector("#saveApi").click();
        })()""")
        await browser.wait_for('document.querySelector("#connection").classList.contains("offline")', "backend failure state")
        await browser.evaluate("""(() => {
          document.querySelector("#settingsButton").click();
          document.querySelector("#apiUrl").value="http://127.0.0.1:8000";
          document.querySelector("#saveApi").click();
        })()""")
        await browser.wait_for('document.querySelector("#connection").classList.contains("online")', "backend recovery")
        print("PASS backend failure and reconnect")

        for width in (1440, 1024, 768, 390):
            await browser.call("Emulation.setDeviceMetricsOverride", {
                "width": width, "height": 900, "deviceScaleFactor": 1, "mobile": False
            })
            await browser.evaluate('window.scrollTo(0,0)')
            await browser.evaluate('new Promise(resolve => setTimeout(resolve, 100))')
            dimensions = await browser.evaluate('({viewport: innerWidth, scroll: document.documentElement.scrollWidth})')
            if dimensions["scroll"] > dimensions["viewport"]:
                offenders = await browser.evaluate("""[...document.querySelectorAll("body *")]
                  .filter(el => el.getBoundingClientRect().right > innerWidth + 2 && getComputedStyle(el).position !== "absolute")
                  .slice(0, 12).map(el => [el.tagName, el.className?.baseVal || el.className, Math.round(el.getBoundingClientRect().right)])""")
                wrapper = await browser.evaluate("""(() => {
                  let e=document.querySelector(".alert-table"), out=[];
                  while(e && out.length<7){let r=e.getBoundingClientRect();out.push([e.tagName,e.className,r.width,r.right,getComputedStyle(e).overflowX,e.scrollWidth]);e=e.parentElement}
                  return out;
                })()""")
                raise AssertionError(f"Horizontal overflow at {width}px: {dimensions}, {offenders}, ancestors={wrapper}")
            if width == 390:
                await browser.screenshot("mobile-hero.png")
            print(f"PASS responsive {width}px")

        await browser.evaluate('document.querySelector("#featuredButton").click()')
        await browser.wait_for('!document.querySelector("#caseContent").hidden', "mobile case")
        dimensions = await browser.evaluate('({viewport: innerWidth, scroll: document.documentElement.scrollWidth})')
        if dimensions["scroll"] > dimensions["viewport"]:
            offenders = await browser.evaluate("""[...document.querySelectorAll("body *")]
              .filter(el => el.getBoundingClientRect().right > innerWidth + 2)
              .slice(0, 15).map(el => [el.tagName, el.className?.baseVal || el.className, el.parentElement?.className, Math.round(el.getBoundingClientRect().right)])""")
            raise AssertionError(f"Mobile investigation overflow: {dimensions}, {offenders}")
        await browser.evaluate('window.scrollTo({top: document.querySelector("#caseContent").getBoundingClientRect().top + scrollY - 75, behavior: "instant"})')
        await browser.evaluate('new Promise(resolve => setTimeout(resolve, 150))')
        await browser.screenshot("mobile-investigation.png")

        assert not browser.exceptions, f"Browser exceptions: {browser.exceptions}"
        unexpected = [entry for entry in browser.console_errors
                      if "bc1qnotarealaddress123456789" not in str(entry)
                      and "127.0.0.1:8999" not in str(entry)]
        assert not unexpected, f"Unexpected browser console errors: {unexpected}"
        print("PASS no page JavaScript exceptions or unexpected console errors")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdp-port", type=int, default=9222)
    args = parser.parse_args()
    asyncio.run(run(args.cdp_port))


if __name__ == "__main__":
    main()
