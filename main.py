import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Загрузка конфигурации
with open('config.json', 'r', encoding='utf-8') as f:
    config = json.load(f)

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix='/', intents=intents)

# Словарь для хранения временных мутов
muted_users = {}

class MuteView(discord.ui.View):
    def __init__(self, member, duration, reason, moderator):
        super().__init__(timeout=60)
        self.member = member
        self.duration = duration
        self.reason = reason
        self.moderator = moderator

    @discord.ui.button(label="✅ Подтвердить", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Вы не можете использовать эту кнопку!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        # Назначение роли "Muted"
        mute_role = discord.utils.get(interaction.guild.roles, name=config['mute_role_name'])
        
        if not mute_role:
            # Создание роли если её нет
            mute_role = await interaction.guild.create_role(
                name=config['mute_role_name'],
                permissions=discord.Permissions(send_messages=False, add_reactions=False, speak=False)
            )
            # Настройка переопределений прав для всех каналов
            for channel in interaction.guild.channels:
                await channel.set_permissions(mute_role, send_messages=False, add_reactions=False, speak=False)
        
        await self.member.add_roles(mute_role, reason=f"Мут от {interaction.user.name}: {self.reason}")
        
        # Сохранение информации о муте
        unmute_time = datetime.now() + self.duration
        muted_users[self.member.id] = unmute_time
        
        embed = discord.Embed(
            title="🔇 Пользователь замьючен",
            description=f"Пользователь {self.member.mention} был замьючен!",
            color=discord.Color.red()
        )
        embed.add_field(name="👤 Модератор", value=interaction.user.mention, inline=True)
        embed.add_field(name="⏱️ Длительность", value=str(self.duration), inline=True)
        embed.add_field(name="📝 Причина", value=self.reason, inline=False)
        embed.add_field(name="⏰ Размут в", value=unmute_time.strftime("%d.%m.%Y %H:%M:%S"), inline=False)
        
        await interaction.followup.send(embed=embed)
        
        # Отправка в лог-канал
        await send_log(interaction.guild, embed)
        
        self.stop()

    @discord.ui.button(label="❌ Отмена", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Вы не можете использовать эту кнопку!", ephemeral=True)
            return
        
        await interaction.response.send_message("✅ Действие отменено!", ephemeral=True)
        self.stop()

class BanView(discord.ui.View):
    def __init__(self, member, reason, moderator, delete_days):
        super().__init__(timeout=60)
        self.member = member
        self.reason = reason
        self.moderator = moderator
        self.delete_days = delete_days

    @discord.ui.button(label="✅ Подтвердить бан", style=discord.ButtonStyle.danger)
    async def confirm_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Вы не можете использовать эту кнопку!", ephemeral=True)
            return
        
        await interaction.response.defer()
        
        try:
            await self.member.ban(reason=f"{interaction.user.name}: {self.reason}", delete_message_days=self.delete_days)
            
            embed = discord.Embed(
                title="🔨 Пользователь забанен",
                description=f"{self.member.mention} был забанен!",
                color=discord.Color.red()
            )
            embed.add_field(name="👤 Модератор", value=interaction.user.mention, inline=True)
            embed.add_field(name="📝 Причина", value=self.reason, inline=False)
            embed.add_field(name="🗑️ Удалено сообщений за", value=f"{self.delete_days} дней", inline=False)
            
            await interaction.followup.send(embed=embed)
            await send_log(interaction.guild, embed)
            
        except discord.Forbidden:
            await interaction.followup.send("❌ У меня недостаточно прав для бана этого пользователя!", ephemeral=True)
        
        self.stop()

    @discord.ui.button(label="❌ Отмена", style=discord.ButtonStyle.secondary)
    async def cancel_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Вы не можете использовать эту кнопку!", ephemeral=True)
            return
        
        await interaction.response.send_message("✅ Бан отменен!", ephemeral=True)
        self.stop()

async def send_log(guild, embed):
    log_channel_name = config['log_channel']
    log_channel = discord.utils.get(guild.channels, name=log_channel_name)
    
    if not log_channel:
        # Создание канала если его нет
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        log_channel = await guild.create_text_channel(log_channel_name, overwrites=overwrites)
    
    await log_channel.send(embed=embed)

def has_permission(interaction, role_list_key):
    """Проверка наличия прав у пользователя"""
    user_roles = [role.name for role in interaction.user.roles]
    allowed_roles = config[role_list_key]
    
    return any(role in user_roles for role in allowed_roles)

def parse_duration(duration_str):
    """Парсинг строки длительности (1h30m45s)"""
    import re
    
    total_seconds = 0
    pattern = re.compile(r'(\d+)([hms])')
    matches = pattern.findall(duration_str.lower())
    
    if not matches:
        raise ValueError("Неверный формат")
    
    for value, unit in matches:
        value = int(value)
        if unit == 'h':
            total_seconds += value * 3600
        elif unit == 'm':
            total_seconds += value * 60
        elif unit == 's':
            total_seconds += value
    
    return total_seconds

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user.name} готов к работе!')
    print(f'📊 На серверах: {len(bot.guilds)}')
    try:
        synced = await bot.tree.sync()
        print(f"✅ Синхронизировано {len(synced)} команд")
    except Exception as e:
        print(f"❌ Ошибка синхронизации: {e}")
    
    # Запуск проверки мутов
    bot.loop.create_task(check_mutes())

async def check_mutes():
    """Проверка и снятие мутов"""
    await bot.wait_until_ready()
    while not bot.is_closed():
        current_time = datetime.now()
        to_unmute = []
        
        for user_id, unmute_time in muted_users.items():
            if current_time >= unmute_time:
                to_unmute.append(user_id)
        
        for user_id in to_unmute:
            for guild in bot.guilds:
                member = guild.get_member(user_id)
                if member:
                    mute_role = discord.utils.get(guild.roles, name=config['mute_role_name'])
                    if mute_role and mute_role in member.roles:
                        await member.remove_roles(mute_role, reason="Время мута истекло")
                        embed = discord.Embed(
                            title="🔊 Пользователь размьючен",
                            description=f"{member.mention} был автоматически размьючен!",
                            color=discord.Color.green()
                        )
                        await send_log(guild, embed)
            
            del muted_users[user_id]
        
        await asyncio.sleep(60)  # Проверка каждую минуту

@bot.tree.command(name="kick", description="Выгнать пользователя с сервера")
@app_commands.describe(member="Пользователь для кика", reason="Причина кика")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    if not has_permission(interaction, 'kick_roles'):
        await interaction.response.send_message("❌ У вас нет прав на использование этой команды!", ephemeral=True)
        return
    
    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("❌ Вы не можете выгнать этого пользователя!", ephemeral=True)
        return
    
    try:
        await member.kick(reason=f"{interaction.user.name}: {reason}")
        
        embed = discord.Embed(
            title="👢 Пользователь кикнут",
            description=f"{member.mention} был кикнут!",
            color=discord.Color.orange()
        )
        embed.add_field(name="👤 Модератор", value=interaction.user.mention, inline=True)
        embed.add_field(name="📝 Причина", value=reason, inline=False)
        
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)
        
    except discord.Forbidden:
        await interaction.response.send_message("❌ У меня недостаточно прав для кика этого пользователя!", ephemeral=True)

@bot.tree.command(name="mute", description="Замьютить пользователя")
@app_commands.describe(
    member="Пользователь для мута",
    duration="Длительность (формат: 1h, 30m, 45s или комбинация 1h30m)",
    reason="Причина мута"
)
async def mute(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "Не указана"):
    if not has_permission(interaction, 'mute_roles'):
        await interaction.response.send_message("❌ У вас нет прав на использование этой команды!", ephemeral=True)
        return
    
    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("❌ Вы не можете замьютить этого пользователя!", ephemeral=True)
        return
    
    # Парсинг длительности
    try:
        total_seconds = parse_duration(duration)
        if total_seconds <= 0:
            await interaction.response.send_message("❌ Неверный формат длительности! Пример: 1h30m или 45s", ephemeral=True)
            return
        
        duration_delta = timedelta(seconds=total_seconds)
    except:
        await interaction.response.send_message("❌ Неверный формат длительности! Пример: 1h30m или 45s", ephemeral=True)
        return
    
    # Создание представления для подтверждения
    view = MuteView(member, duration_delta, reason, interaction.user)
    
    embed = discord.Embed(
        title="⚠️ Подтверждение мута",
        description=f"Вы уверены, что хотите замьютить {member.mention}?",
        color=discord.Color.yellow()
    )
    embed.add_field(name="⏱️ Длительность", value=duration, inline=True)
    embed.add_field(name="📝 Причина", value=reason, inline=False)
    
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="ban", description="Забанить пользователя")
@app_commands.describe(member="Пользователь для бана", reason="Причина бана", delete_messages="Удалить сообщения (дни)")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана", delete_messages: int = 0):
    if not has_permission(interaction, 'ban_roles'):
        await interaction.response.send_message("❌ У вас нет прав на использование этой команды!", ephemeral=True)
        return
    
    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("❌ Вы не можете забанить этого пользователя!", ephemeral=True)
        return
    
    view = BanView(member, reason, interaction.user, delete_messages)
    
    embed = discord.Embed(
        title="⚠️ Подтверждение бана",
        description=f"Вы уверены, что хотите забанить {member.mention}?",
        color=discord.Color.yellow()
    )
    embed.add_field(name="📝 Причина", value=reason, inline=False)
    embed.add_field(name="🗑️ Удалить сообщения за", value=f"{delete_messages} дней", inline=False)
    
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="unmute", description="Снять мут с пользователя")
@app_commands.describe(member="Пользователь для размута", reason="Причина размута")
async def unmute(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    if not has_permission(interaction, 'mute_roles'):
        await interaction.response.send_message("❌ У вас нет прав на использование этой команды!", ephemeral=True)
        return
    
    mute_role = discord.utils.get(interaction.guild.roles, name=config['mute_role_name'])
    
    if not mute_role or mute_role not in member.roles:
        await interaction.response.send_message("❌ Этот пользователь не замьючен!", ephemeral=True)
        return
    
    try:
        await member.remove_roles(mute_role, reason=f"{interaction.user.name}: {reason}")
        
        # Удаление из словаря мутов
        if member.id in muted_users:
            del muted_users[member.id]
        
        embed = discord.Embed(
            title="🔊 Пользователь размьючен",
            description=f"{member.mention} был размьючен!",
            color=discord.Color.green()
        )
        embed.add_field(name="👤 Модератор", value=interaction.user.mention, inline=True)
        embed.add_field(name="📝 Причина", value=reason, inline=False)
        
        await interaction.response.send_message(embed=embed)
        await send_log(interaction.guild, embed)
        
    except discord.Forbidden:
        await interaction.response.send_message("❌ У меня недостаточно прав для размута этого пользователя!", ephemeral=True)

@bot.tree.command(name="config", description="Показать текущую конфигурацию")
async def show_config(interaction: discord.Interaction):
    if not has_permission(interaction, 'admin_roles'):
        await interaction.response.send_message("❌ У вас нет прав на использование этой команды!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="⚙️ Конфигурация бота",
        color=discord.Color.blue()
    )
    
    for key, value in config.items():
        if isinstance(value, list):
            value = ", ".join(value)
        embed.add_field(name=key, value=value, inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="help", description="Показать список команд")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 Команды бота _NorthBears_",
        description="Список доступных команд",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="👢 /kick",
        value="Выгнать пользователя\nИспользование: `/kick @пользователь причина`",
        inline=False
    )
    embed.add_field(
        name="🔇 /mute",
        value="Замьютить пользователя\nИспользование: `/mute @пользователь 1h30m причина`",
        inline=False
    )
    embed.add_field(
        name="🔊 /unmute",
        value="Снять мут\nИспользование: `/unmute @пользователь причина`",
        inline=False
    )
    embed.add_field(
        name="🔨 /ban",
        value="Забанить пользователя\nИспользование: `/ban @пользователь причина дни`",
        inline=False
    )
    embed.add_field(
        name="⚙️ /config",
        value="Показать конфигурацию\nТолько для администраторов",
        inline=False
    )
    
    embed.set_footer(text="Настройка ролей в config.json")
    
    await interaction.response.send_message(embed=embed)

# Запуск бота
if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("❌ Токен не найден! Проверьте файл .env")
    else:
        bot.run(token)