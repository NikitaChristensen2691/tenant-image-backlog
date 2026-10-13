from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from saas_image_backlog.infrai_images import InfraiImages
from saas_image_backlog.tenant_backlog import BacklogItem, TenantBacklog


async def run(paths: list[Path], aspect: str) -> None:
    api_key = os.environ["INFRAI_API_KEY"]
    gateway = InfraiImages(api_key)
    try:
        backlog = TenantBacklog(gateway)
        backlog.onboard("founder-demo")
        results = await backlog.process(
            "founder-demo",
            [BacklogItem(path=path, aspect=aspect) for path in paths],
        )
        for result in results:
            print(f"{result.source}: {result.output}")
    finally:
        await gateway.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Drain a tenant image backlog")
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--aspect", default="1:1")
    args = parser.parse_args()
    asyncio.run(run(args.images, args.aspect))


if __name__ == "__main__":
    main()

