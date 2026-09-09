import asyncio, httpx


from mcp import Client


from mcp.client.streamable_http import streamable_http_client

async def main():


    url = 'https://mcp.regentplatform.com/api/mcp'  # or whatever the row's url is


    async with streamable_http_client(url) as (read, write, _):


        async with Client(read, write) as c:


            tools = await c.list_tools()


            print('TOOLS:', [t.name for t in tools])

asyncio.run(main())