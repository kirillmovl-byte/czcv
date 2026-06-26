import discord
from discord.ext import commands
from discord import app_commands
import asyncio
import json
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import aiohttp

# ============================================================
# 🔧 НАСТРОЙКИ РОЛЕЙ (ИЗМЕНЯЙТЕ ЗДЕСЬ)
# ============================================================
ADMIN_ROLES = ["🥶owner🤗, 🥳|Co-owner|🥰"]           
MODERATOR_ROLES = ["[STAFF]"]         
KICK_ROLES = ["[STAFF]"]  
MUTE_ROLES = ["[STAFF]"]  
BAN_ROLES = ["[STAFF]"]                         
LOG_CHANNEL = "logs"                                           
MUTE_ROLE_NAME = "Muted"                                       
# ============================================================

# Загрузка переменных окружения
load_dotenv()

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix='/', intents=intents)

# Словарь для хранения временных мутов
muted_users = {}

# ============================================================
# 🖼️ ФУНКЦИЯ ДЛЯ СОЗДАНИЯ КАРТИНКИ С АВАТАРКОЙ БОТА
# ============================================================

async def create_bot_image(text, title, color="#4A90D9"):
    """
    Создает изображение с аватаркой бота на синем фоне
    """
    # Создаем фон
    img = Image.new('RGB', (800, 400), color=color)
    draw = ImageDraw.Draw(img)
    
    # Пытаемся загрузить аватарку бота
    try:
        if bot.user and bot.user.avatar:
            avatar_url = bot.user.avatar.url
            async with aiohttp.ClientSession() as session:
                async with session.get(avatar_url) as resp:
                    if resp.status == 200:
                        avatar_data = await resp.read()
                        avatar_img = Image.open(BytesIO(avatar_data))
                        avatar_img = avatar_img.resize((150, 150))
                        # Делаем круглую аватарку
                        mask = Image.new('L', (150, 150), 0)
                        mask_draw = ImageDraw.Draw(mask)
                        mask_draw.ellipse((0, 0, 150, 150), fill=255)
                        avatar_img.putalpha(mask)
                        # Вставляем аватарку на фон
                        img.paste(avatar_img, (50, 125), avatar_img)
    except:
        pass  # Если не удалось загрузить аватарку, пропускаем
    
    # Рисуем круглый фон для аватарки (если нет аватарки)
    if not bot.user or not bot.user.avatar:
        draw.ellipse((50, 125, 200, 275), fill="#2ECC71", outline="#FFFFFF", width=5)
        draw.text((90, 185), "🐻", font=None, fill="white")
    
    # Добавляем текст
    try:
        # Пытаемся загрузить шрифт
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        font_text = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except:
        font_title = ImageFont.load_default()
        font_text = ImageFont.load_default()
    
    # Название бота
    bot_name = bot.user.name if bot.user else "NorthBears"
    draw.text((250, 140), f"🐻 {bot_name}", fill="white", font=font_title)
    
    # Основной текст (название команды)
    draw.text((250, 200), title, fill="#FFFFFF", font=font_text)
    
    # Дополнительный текст
    draw.text((250, 250), text, fill="#E8E8E8", font=font_text)
    
    # Нижний колонтитул
    draw.text((50, 360), "NorthBears Bot", fill="#FFFFFF", font=font_text)
    draw.text((650, 360), datetime.now().strftime("%d.%m.%Y %H:%M"), fill="#FFFFFF", font=font_text)
    
    # Сохраняем в BytesIO
    img_buffer = BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    
    return img_buffer

async def send_with_image(interaction, title, description, color="#4A90D9", footer=None):
    """Отправляет сообщение с картинкой"""
    img_buffer = await create_bot_image(description, title, color)
    file = discord.File(img_buffer, filename="northbears.png")
    
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color.blue()
    )
    embed.set_image(url="attachment://northbears.png")
    embed.set_footer(text=footer or "NorthBears Bot 🐻")
    embed.timestamp = datetime.now()
    
    await interaction.response.send_message(embed=embed, file=file)

# ============================================================
# ФУНКЦИЯ ДЛЯ ПРОВЕРКИ ПРАВ
# ============================================================

def has_permission(interaction, required_roles):
    """Проверяет наличие прав у пользователя"""
    user_roles = [role.name for role in interaction.user.roles]
    return any(role in user_roles for role in required_roles)

# ============================================================
# КЛАССЫ ДЛЯ КНОПОК
# ============================================================

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
        
        mute_role = discord.utils.get(interaction.guild.roles, name=MUTE_ROLE_NAME)
        
        if not mute_role:
            mute_role = await interaction.guild.create_role(
                name=MUTE_ROLE_NAME,
                permissions=discord.Permissions(send_messages=False, add_reactions=False, speak=False)
            )
            for channel in interaction.guild.channels:
                await channel.set_permissions(mute_role, send_messages=False, add_reactions=False, speak=False)
        
        await self.member.add_roles(mute_role, reason=f"Мут от {interaction.user.name}: {self.reason}")
        
        unmute_time = datetime.now() + self.duration
        muted_users[self.member.id] = unmute_time
        
        # Отправляем с картинкой
        await send_with_image(
            interaction,
            "🔇 Пользователь замьючен",
            f"{self.member.mention} был замьючен!\n⏱️ Длительность: {str(self.duration)}\n👤 Модератор: {interaction.user.mention}\n📝 Причина: {self.reason}\n⏰ Размут в: {unmute_time.strftime('%d.%m.%Y %H:%M:%S')}"
        )
        
        await send_log(interaction.guild, f"🔇 {self.member} замьючен модератором {interaction.user}\nПричина: {self.reason}\nДлительность: {self.duration}")
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
            
            await send_with_image(
                interaction,
                "🔨 Пользователь забанен",
                f"{self.member.mention} был забанен!\n👤 Модератор: {interaction.user.mention}\n📝 Причина: {self.reason}\n🗑️ Удалено сообщений за: {self.delete_days} дней"
            )
            
            await send_log(interaction.guild, f"🔨 {self.member} забанен модератором {interaction.user}\nПричина: {self.reason}")
            
        except discord.Forbidden:
            await interaction.response.send_message("❌ У меня недостаточно прав для бана этого пользователя!", ephemeral=True)
        
        self.stop()

    @discord.ui.button(label="❌ Отмена", style=discord.ButtonStyle.secondary)
    async def cancel_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Вы не можете использовать эту кнопку!", ephemeral=True)
            return
        await interaction.response.send_message("✅ Бан отменен!", ephemeral=True)
        self.stop()

# ============================================================
# ФУНКЦИЯ ДЛЯ ЛОГОВ
# ============================================================

async def send_log(guild, message):
    log_channel = discord.utils.get(guild.channels, name=LOG_CHANNEL)
    if not log_channel:
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True)
        }
        log_channel = await guild.create_text_channel(LOG_CHANNEL, overwrites=overwrites)
    
    embed = discord.Embed(
        title="📋 Лог",
        description=message,
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    await log_channel.send(embed=embed)

# ============================================================
# ПАРСИНГ ДЛИТЕЛЬНОСТИ
# ============================================================

def parse_duration(duration_str):
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

# ============================================================
# СОБЫТИЯ БОТА
# ============================================================

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user.name} готов к работе!')
    print(f'📊 На серверах: {len(bot.guilds)}')
    try:
        synced = await bot.tree.sync()
        print(f"✅ Синхронизировано {len(synced)} команд")
    except Exception as e:
        print(f"❌ Ошибка синхронизации: {e}")
    
    bot.loop.create_task(check_mutes())

async def check_mutes():
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
                    mute_role = discord.utils.get(guild.roles, name=MUTE_ROLE_NAME)
                    if mute_role and mute_role in member.roles:
                        await member.remove_roles(mute_role, reason="Время мута истекло")
                        await send_log(guild, f"🔊 {member} автоматически размьючен (время истекло)")
            
            del muted_users[user_id]
        
        await asyncio.sleep(60)

# ============================================================
# КОМАНДЫ БОТА
# ============================================================

@bot.tree.command(name="kick", description="Выгнать пользователя с сервера")
@app_commands.describe(member="Пользователь для кика", reason="Причина кика")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    if not has_permission(interaction, KICK_ROLES):
        await interaction.response.send_message("❌ У вас нет прав на использование этой команды!", ephemeral=True)
        return
    
    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("❌ Вы не можете выгнать этого пользователя!", ephemeral=True)
        return
    
    try:
        await member.kick(reason=f"{interaction.user.name}: {reason}")
        
        await send_with_image(
            interaction,
            "👢 Пользователь кикнут",
            f"{member.mention} был кикнут!\n👤 Модератор: {interaction.user.mention}\n📝 Причина: {reason}"
        )
        
        await send_log(interaction.guild, f"👢 {member} кикнут модератором {interaction.user}\nПричина: {reason}")
        
    except discord.Forbidden:
        await interaction.response.send_message("❌ У меня недостаточно прав для кика этого пользователя!", ephemeral=True)

@bot.tree.command(name="mute", description="Замьютить пользователя")
@app_commands.describe(
    member="Пользователь для мута",
    duration="Длительность (формат: 1h, 30m, 45s или комбинация 1h30m)",
    reason="Причина мута"
)
async def mute(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "Не указана"):
    if not has_permission(interaction, MUTE_ROLES):
        await interaction.response.send_message("❌ У вас нет прав на использование этой команды!", ephemeral=True)
        return
    
    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("❌ Вы не можете замьютить этого пользователя!", ephemeral=True)
        return
    
    try:
        total_seconds = parse_duration(duration)
        if total_seconds <= 0:
            await interaction.response.send_message("❌ Неверный формат длительности! Пример: 1h30m или 45s", ephemeral=True)
            return
        duration_delta = timedelta(seconds=total_seconds)
    except:
        await interaction.response.send_message("❌ Неверный формат длительности! Пример: 1h30m или 45s", ephemeral=True)
        return
    
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
    if not has_permission(interaction, BAN_ROLES):
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
    if not has_permission(interaction, MUTE_ROLES):
        await interaction.response.send_message("❌ У вас нет прав на использование этой команды!", ephemeral=True)
        return
    
    mute_role = discord.utils.get(interaction.guild.roles, name=MUTE_ROLE_NAME)
    
    if not mute_role or mute_role not in member.roles:
        await interaction.response.send_message("❌ Этот пользователь не замьючен!", ephemeral=True)
        return
    
    try:
        await member.remove_roles(mute_role, reason=f"{interaction.user.name}: {reason}")
        
        if member.id in muted_users:
            del muted_users[member.id]
        
        await send_with_image(
            interaction,
            "🔊 Пользователь размьючен",
            f"{member.mention} был размьючен!\n👤 Модератор: {interaction.user.mention}\n📝 Причина: {reason}"
        )
        
        await send_log(interaction.guild, f"🔊 {member} размьючен модератором {interaction.user}\nПричина: {reason}")
        
    except discord.Forbidden:
        await interaction.response.send_message("❌ У меня недостаточно прав для размута этого пользователя!", ephemeral=True)

@bot.tree.command(name="config", description="Показать текущую конфигурацию")
async def show_config(interaction: discord.Interaction):
    if not has_permission(interaction, ADMIN_ROLES):
        await interaction.response.send_message("❌ У вас нет прав на использование этой команды!", ephemeral=True)
        return
    
    config_text = f"""
**📋 Текущая конфигурация:**

**Администраторы:** {', '.join(ADMIN_ROLES)}
**Модераторы:** {', '.join(MODERATOR_ROLES)}
**Кто может кикать:** {', '.join(KICK_ROLES)}
**Кто может мутить:** {', '.join(MUTE_ROLES)}
**Кто может банить:** {', '.join(BAN_ROLES)}
**Канал логов:** #{LOG_CHANNEL}
**Роль мута:** {MUTE_ROLE_NAME}
"""
    
    await send_with_image(
        interaction,
        "⚙️ Конфигурация бота",
        config_text
    )

@bot.tree.command(name="help", description="Показать список команд")
async def help_command(interaction: discord.Interaction):
    help_text = """
**📚 Команды бота:**

👢 `/kick @пользователь причина` - Выгнать пользователя
🔇 `/mute @пользователь 1h30m причина` - Замьютить
🔊 `/unmute @пользователь причина` - Снять мут
🔨 `/ban @пользователь причина дни` - Забанить
⚙️ `/config` - Показать конфигурацию (только админы)
📖 `/help` - Эта помощь

**Форматы длительности:** 1h, 30m, 45s, 1h30m45s
"""
    
    await send_with_image(
        interaction,
        "📚 Помощь по командам",
        help_text
    )

# ============================================================
# ЗАПУСК БОТА
# ============================================================

if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("❌ Токен не найден! Проверьте переменную окружения DISCORD_TOKEN")
    else:
        bot.run(token)
