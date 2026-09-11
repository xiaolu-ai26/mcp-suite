# In-process schema check: imports core.server (no HTTP, no token) and inspects every tool's inputSchema.
# Run from the code root with MCP_DB_PATH pointing at a throwaway file.
import asyncio, json, sys
sys.dont_write_bytecode = True
import core.server as s

async def main():
    bad = []
    for name, tool in sorted((await s.mcp.get_tools()).items()):
        schema = tool.to_mcp_tool().inputSchema
        text = json.dumps(schema)
        notype = [p for p, v in schema.get("properties", {}).items() if "type" not in v]
        combo = any(k in text for k in ('"anyOf"', '"oneOf"', '"allOf"'))
        print(f"{s.PRODUCT} {name}: params={len(schema.get('properties', {}))} anyOf/oneOf={combo} missing_type={notype}")
        if combo or notype:
            bad.append(name)
    print("RESULT", "FAIL" if bad else "OK", bad)

asyncio.run(main())
