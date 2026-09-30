#!/usr/bin/env python3
"""CDP helpers for Grok Bot.app on localhost:9222.

Launch (quit first if already running without CDP):

    open -a "Grok Bot" --args --remote-debugging-port=9222 --force-renderer-accessibility

Probe:

    curl -sS http://127.0.0.1:9222/json/list
"""
from __future__ import annotations

import asyncio
import json
import urllib.request

import websockets

CDP = "http://127.0.0.1:9222/json/list"
PORT = 9222


def page_ws() -> str:
    pages = json.loads(urllib.request.urlopen(CDP, timeout=3).read())
    page = next(p for p in pages if p.get("title") == "Grok Bot" and p.get("type") == "page")
    return page["webSocketDebuggerUrl"]


class GrokCDP:
    def __init__(self, ws):
        self.ws = ws
        self.sid = 1

    async def call(self, method, params=None):
        self.sid += 1
        sid = self.sid
        await self.ws.send(json.dumps({"id": sid, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == sid:
                if "error" in msg:
                    raise RuntimeError(msg["error"])
                return msg.get("result", {})

    async def ev(self, expr):
        r = await self.call(
            "Runtime.evaluate",
            {"expression": expr, "returnByValue": True, "awaitPromise": True},
        )
        if r.get("exceptionDetails"):
            raise RuntimeError(str(r["exceptionDetails"])[:800])
        return r.get("result", {}).get("value")

    async def mouse_click(self, x: float, y: float) -> None:
        await self.call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
        await asyncio.sleep(0.05)
        await self.call(
            "Input.dispatchMouseEvent",
            {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1},
        )
        await self.call(
            "Input.dispatchMouseEvent",
            {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1},
        )

    async def click_aria(self, aria: str) -> str:
        return await self.ev(
            f"""(() => {{
              const b=[...document.querySelectorAll('button')].find(x => (x.getAttribute('aria-label')||'') === {json.dumps(aria)});
              if(!b) return 'missing';
              b.click(); return 'clicked';
            }})()"""
        )

    async def click_btn_text(self, text: str, exact=False) -> str:
        cond = (
            "t===want || a===want"
            if exact
            else 't===want || t.split("\\n")[0]===want || a===want || t.includes(want)'
        )
        return await self.ev(
            f"""(() => {{
              const want = {json.dumps(text)};
              const b=[...document.querySelectorAll('button')].find(x => {{
                const t=(x.innerText||'').trim();
                const a=x.getAttribute('aria-label')||'';
                return {cond};
              }});
              if(!b) return 'missing';
              b.click(); return 'clicked:'+((b.getAttribute('aria-label')||b.innerText||'').slice(0,40));
            }})()"""
        )

    async def open_bot(self, name: str) -> None:
        r = await self.click_btn_text(name)
        if r == "missing":
            r = await self.ev(
                f"""(() => {{
                  const want={json.dumps(name)};
                  const b=[...document.querySelectorAll('button')].find(x => (x.getAttribute('aria-label')||'').includes(want) || (x.innerText||'').includes(want));
                  if(!b) return 'missing';
                  b.click(); return 'clicked';
                }})()"""
            )
        if r == "missing":
            raise RuntimeError(f"bot not found: {name}")
        await asyncio.sleep(0.7)
        await self.ev("""(() => {
          const closeish = [...document.querySelectorAll('button')].find(x => x.getAttribute('aria-label')==='詳細に戻る');
          if(closeish) { closeish.click(); }
          return true;
        })()""")
        await asyncio.sleep(0.5)
        opened = await self.click_aria("会話の詳細を表示")
        if opened == "clicked":
            await asyncio.sleep(0.8)

    async def open_settings(self) -> None:
        has = await self.ev("""!!document.querySelector('textarea[aria-label="Botの説明"]')""")
        if has:
            return
        r = await self.click_aria("Botの設定")
        if r == "missing":
            await self.click_aria("会話の詳細を表示")
            await asyncio.sleep(0.6)
            r = await self.click_aria("Botの設定")
        if r == "missing":
            raise RuntimeError("Botの設定 not found")
        await asyncio.sleep(0.8)

    async def back_from_settings(self) -> None:
        await self.click_aria("詳細に戻る")
        await asyncio.sleep(0.8)

    async def read_instructions(self) -> dict:
        return await self.ev("""(() => {
          const ta=document.querySelector('textarea[aria-label="Botの説明"]');
          const name=document.querySelector('input[aria-label="Bot名"]');
          const label=document.querySelector('input[aria-label="Botのラベル"]');
          if(!ta) return {ok:false};
          return {ok:true, name: name && name.value, label: label && label.value, text: ta.value, len: ta.value.length};
        })()""")

    async def set_instructions(self, text: str) -> dict:
        payload = json.dumps(text)
        return await self.ev(
            f"""(() => {{
              const ta=document.querySelector('textarea[aria-label="Botの説明"]');
              if(!ta) return {{ok:false, reason:'NO_TA'}};
              const props=ta[Object.keys(ta).find(k=>k.startsWith('__reactProps'))];
              const tracker=ta._valueTracker;
              const native=Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype,'value').set;
              if(tracker) tracker.setValue(ta.value);
              native.call(ta, {payload});
              props && props.onChange && props.onChange({{target: ta, currentTarget: ta, persist(){{}}}});
              ta.dispatchEvent(new Event('input', {{bubbles:true}}));
              ta.dispatchEvent(new Event('change', {{bubbles:true}}));
              ta.blur();
              props && props.onBlur && props.onBlur({{target: ta, currentTarget: ta, persist(){{}}}});
              return {{ok:true, len: ta.value.length}};
            }})()"""
        )

    async def pane_text(self) -> str:
        return await self.ev("""(() => {
          const pane=document.querySelector('.sand-info-pane');
          return pane ? pane.innerText.slice(0,4000) : '';
        })()""")

    async def pane_buttons(self) -> list:
        return await self.ev("""(() => {
          const pane=document.querySelector('.sand-info-pane');
          if(!pane) return [];
          return [...pane.querySelectorAll('button')].map(b => ({
            aria: b.getAttribute('aria-label'),
            text: (b.innerText||'').trim().slice(0,120)
          }));
        })()""")


async def connect() -> tuple:
    ws = await websockets.connect(page_ws(), max_size=50_000_000)
    g = GrokCDP(ws)
    await g.call("Runtime.enable")
    return ws, g
