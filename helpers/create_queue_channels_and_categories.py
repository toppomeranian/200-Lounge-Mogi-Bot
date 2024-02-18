import logging
import DBA
from . import FormatVote
from helpers.getters import get_lounge_guild
from helpers.getters import get_unix_time_now
from helpers import create_teams
from config import UPDATER_ROLE_ID, LOUNGE_QUEUE_CATEGORY_POSITION
from discord import PermissionOverwrite
import asyncio

async def create_queue_channels_and_categories(client, number_of_players, groups_of_12):
    """Creates channels for lounge queue based on # of players"""
    guild = get_lounge_guild(client)
    if guild is None:
        print('create_queue_channels_and_categories error: Guild not found')
        return False
    
    print(f'length of groups: {len(groups_of_12)}')
    print(f'groups: {groups_of_12}')
    
    # each group = channel
    # each instance of 25 channels needs category
    # handle groups_of_12
    # assign permissions to channel for each user in group
    channel_count = 0
    category_count = 1
    vote_tasks_info = []
    for group in groups_of_12:
        if channel_count % 25 == 0: # 25 channels per category
            # Create category
            category_name = f'Rooms {category_count}'
            category = await guild.create_category(category_name)
            await category.edit(position=LOUNGE_QUEUE_CATEGORY_POSITION)
            category_id = category.id
            category_count += 1
            # Category to DB
            try:
                with DBA.DBAccess() as db:
                    db.execute('INSERT INTO lounge_queue_category (category_id) VALUES (%s)', (category_id,))
            except Exception as e:
                logging.warning(f'Exception inserting specific category to lounge_queue_category table: {e}')
                return False
            
        # Create channel
        channel_name = f"Room {channel_count}"
        channel = await guild.create_text_channel(channel_name, category=category)
        channel_id = channel.id
        channel_count += 1
        lounge_staff = guild.get_role(UPDATER_ROLE_ID)
        if lounge_staff is None:
            logging.warning('create_queue_channels_and_categories oops | oops no staff in channel omg')
        lounge_staff_permissions = PermissionOverwrite(view_channel=True, send_messages=True)
        await channel.set_permissions(lounge_staff, overwrite=lounge_staff_permissions)
        await channel.set_permissions(guild.default_role, view_channel=False)
        # Average mmr calculation
        total_mmr = 0
        player_list = []
        player_room_initialization_string = ''
        for player_id, (mmr, _) in group:
            player_room_initialization_string += f'<@{player_id}> : `{mmr}` MMR\n'
            player_list.append(player_id)
            total_mmr += mmr
            # Assign permissions for player in channel
            try:
                user = guild.get_member(player_id)
                permissions = PermissionOverwrite(view_channel=True, send_messages=True)
                await channel.set_permissions(user, overwrite=permissions)
            except Exception:
                continue
        average_mmr = int(total_mmr/12)
        mmrs = [player[1][0] for player in group]
        max_mmr = max(mmrs)
        min_mmr = min(mmrs)
        
        # Channel to DB
        try:
            with DBA.DBAccess() as db:
                db.execute('INSERT INTO lounge_queue_channel (channel_id, category_id, average_mmr, max_mmr, min_mmr) VALUES (%s, %s, %s, %s, %s);', (channel_id, category_id, average_mmr, max_mmr, min_mmr))
        except Exception as e:
            logging.warning(f'Exception inserting channel into lounge_queue_category | {e}')
            return False
        
        # Remove players from lounge queue
        for player in player_list:
            try:
                with DBA.DBAccess() as db:
                    db.execute('DELETE FROM lounge_queue_player WHERE player_id = %s;', (player,))
            except Exception as e:
                logging.warning(f'create_queue_channels_and_categories error | could not remove player from lounge_queue_player | {e}')
                        
        # ping each player
        pingable_player_list = []
        for player in player_list:
            pingable_player_list.append(f'<@{player}>,')
        clean_pingable_player_list = ' '.join(pingable_player_list)
        
        # Create format vote view
        format_vote_view = FormatVote(client, player_list, clean_pingable_player_list, channel_id)
        format_vote_task = client.loop.create_task(format_vote_view.run())
        vote_tasks_info.append((format_vote_task, format_vote_view, channel_id))
        
    # Wait for all votes to complete
    await asyncio.gather(*[task_info[0] for task_info in vote_tasks_info])

    # Process each vote's result
    for _, format_vote_view, channel_id in vote_tasks_info:
        vote_result = await format_vote_view.get_result()
        channel = client.get_channel(channel_id)

        # Process the vote result for each channel
        response_string = await create_teams(client, format_vote_view.uid_list, vote_result, average_mmr)
        await channel.send(response_string)

        # Send final room start time message
        unix_now = await get_unix_time_now()
        room_open_time = unix_now + 120
        penalty_time = room_open_time + 360
        await channel.send(f'Open room at: <t:{room_open_time}:t>\nPenalty at: <t:{penalty_time}:t>')

    print("Creation complete.")
    return True