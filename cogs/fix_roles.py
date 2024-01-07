from discord.ext import commands
from helpers import set_uid_roles

class FixRolesCog(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.slash_command(
        name='fix_roles',
        description='Fixes player roles and nickname'
    )
    async def fix_roles(self, ctx):
        await ctx.defer()
        response = await set_uid_roles(self.client, ctx.author.id)
        if response:
            await ctx.respond(f'Player roles set for <@{ctx.author.id}>')
        else:
            await ctx.respond('`Error 79b:` Could not set roles')

def setup(client):
    client.add_cog(FixRolesCog(client))