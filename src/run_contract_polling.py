from __future__ import annotations

import argparse

from contract_sentinel.poller import ContractApprovalPoller
from contract_sentinel.settings import load_settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Poll OA contract approval workflows.")
    parser.add_argument("--once", action="store_true", help="Run one polling cycle and exit.")
    args = parser.parse_args()

    settings = load_settings()
    poller = ContractApprovalPoller(settings)

    if args.once:
        with poller.client.open_browser() as playwright:
            browser = playwright.chromium.launch(headless=False)
            context = browser.new_context()
            context.add_cookies(poller.client.load_cookies())
            page = context.new_page()
            try:
                count = poller.process_once_with_page(page)
                print(f"processed={count}")
            finally:
                browser.close()
        return

    poller.run_forever()


if __name__ == "__main__":
    main()
