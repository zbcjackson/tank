"""QR code login flow for WeChat iLink Bot API.

Run as: python -m connector_wechat.login [--state-dir DIR]

Displays a QR code in the terminal, waits for the user to scan with
WeChat mobile, then saves credentials to the state directory.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path


async def _run_login(state_dir: Path) -> None:
    from .ilink_client import ILinkClient
    from .state import WeChatState

    # Use a temporary client with empty credentials for QR request
    client = ILinkClient("", "", base_url="https://ilinkai.weixin.qq.com")
    await client.open()

    try:
        print("Requesting QR code from iLink Bot API...")
        qr_data = await client.request_qr_code()
        qrcode_token = qr_data.get("qrcode", "")
        qr_url = qr_data.get("qrcode_img_content", "") or qr_data.get("qr_url", "") or qr_data.get("url", "")

        if not qrcode_token:
            print(f"ERROR: Failed to get QR code. Response: {qr_data}", file=sys.stderr)
            sys.exit(1)

        if qr_url:
            _display_qr(qr_url)
        else:
            print(f"QR token received: {qrcode_token}")
            print("(Could not determine QR image URL from response)")

        print("\nScan the QR code with WeChat, then confirm login on your phone.")
        print("Waiting for scan...")

        # Poll for scan status
        max_attempts = 60  # ~2 minutes with 2s intervals
        for attempt in range(max_attempts):
            await asyncio.sleep(2)
            status = await client.poll_qr_status(qrcode_token)

            state_str = status.get("status", "")

            if state_str == "confirmed":
                # Success — credentials are in the response
                account_id = (
                    status.get("ilink_bot_id", "")
                    or status.get("account_id", "")
                    or status.get("bot_id", "")
                )
                token = status.get("bot_token", "") or status.get("token", "")
                user_id = status.get("ilink_user_id", "")

                if not account_id or not token:
                    print(f"ERROR: Login succeeded but missing credentials: {status}", file=sys.stderr)
                    sys.exit(1)

                state = WeChatState(state_dir)
                state.save_credentials(account_id, token)

                print(f"\n微信连接成功，account_id={account_id}")
                print(f"Credentials saved to: {state_dir}/credentials.json")
                print("\nSet these in your .env:")
                print(f"  WECHAT_ACCOUNT_ID={account_id}")
                print(f"  WECHAT_TOKEN={token}")
                if user_id:
                    print("\nYour personal WeChat user ID (for allowlist rules):")
                    print(f"  wechat:user:{user_id}")
                return

            if state_str == "scaned":
                # QR scanned, waiting for confirmation
                if attempt == 0 or attempt % 5 == 0:
                    print("QR scanned! Waiting for confirmation...")
            elif state_str == "expired":
                # QR expired
                print("QR code expired. Please restart the login flow.")
                sys.exit(1)
            # else: "wait" — still waiting for scan

        print("Timeout waiting for QR scan. Please try again.")
        sys.exit(1)

    finally:
        await client.close()


def _display_qr(url: str) -> None:
    """Display QR code in terminal, or fall back to URL."""
    try:
        import qrcode  # type: ignore[import-untyped]
        qr = qrcode.QRCode(error_correction=qrcode.ERROR_CORRECT_L)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except ImportError:
        print(f"\nQR URL (open in browser or scan): {url}")
        print("(Install 'qrcode' package for terminal QR display: pip install qrcode)")


def main() -> None:
    parser = argparse.ArgumentParser(description="WeChat iLink Bot QR Login")
    parser.add_argument(
        "--state-dir",
        type=str,
        default=str(Path.home() / ".tank" / "wechat" / "default"),
        help="Directory to save credentials (default: ~/.tank/wechat/default)",
    )
    args = parser.parse_args()
    asyncio.run(_run_login(Path(args.state_dir)))


if __name__ == "__main__":
    main()
