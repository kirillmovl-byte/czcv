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
# 🔧 НАСТРОЙКИ (ИЗМЕНЯЙТЕ ЗДЕСЬ)
# ============================================================
MASTER_ADMIN = "bridyt"  # 👑 ГЛАВНЫЙ АДМИНИСТРАТОР (по нику)

# БАЗОВЫЕ РОЛИ (будут храниться в файле)
DEFAULT_ADMIN_ROLES = ["Administrator", "Admin"]
DEFAULT_MODERATOR_ROLES = ["Moderator", "Модератор"]
DEFAULT_KICK_ROLES = ["Administrator", "Admin", "Модератор", "Moderator"]
DEFAULT_MUTE_ROLES = ["Administrator", "Admin", "Модератор", "Moderator"]
DEFAULT_BAN_ROLES = ["Administrator", "Admin"]

LOG_CHANNEL = "logs"
MUTE_ROLE_NAME = "Muted"
# ============================================================

# Загрузка переменных окружения
load_dotenv()

# Файл для хранения настроек
SETTINGS_FILE = "settings.json"

# Загрузка настроек из файла
def load_settings():
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return {
            "admin_roles": DEFAULT_ADMIN_ROLES,
            "moderator_roles": DEFAULT_MODERATOR_ROLES,
            "kick_roles": DEFAULT_KICK_ROLES,
            "mute_roles": DEFAULT_MUTE_ROLES,
            "ban_roles": DEFAULT_BAN_ROLES,
            "admin_users": [],  # ID пользователей-администраторов
            "moderator_users": []  # ID пользователей-модераторов
        }

def save_settings(settings):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=4, ensure_ascii=False)

# Загружаем настройки
settings = load_settings()

# Настройки бота
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

bot = commands.Bot(command_prefix='/', intents=intents)

# Словарь для хранения временных мутов
muted_users = {}

# ============================================================
# 🖼️ ФУНКЦИЯ ДЛЯ СОЗДАНИЯ КАРТИНКИ
# ============================================================

async def create_bot_image(text, title, color="#4A90D9"):
    img = Image.new('RGB', (800, 450), color=color)
    draw = ImageDraw.Draw(img)
    
    try:
        if bot.user and bot.user.avatar:
            avatar_url = bot.user.avatar.url
            async with aiohttp.ClientSession() as session:
                async with session.get(avatar_url) as resp:
                    if resp.status == 200:
                        avatar_data = await resp.read()
                        avatar_img = Image.open(BytesIO(avatar_data))
                        avatar_img = avatar_img.resize((150, 150))
                        mask = Image.new('L', (150, 150), 0)
                        mask_draw = ImageDraw.Draw(mask)
                        mask_draw.ellipse((0, 0, 150, 150), fill=255)
                        avatar_img.putalpha(mask)
                        img.paste(avatar_img, (50, 150), avatar_img)
    except:
        pass
    
    try:
        font_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
        font_text = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    except:
        font_title = ImageFont.load_default()
        font_text = ImageFont.load_default()
    
    bot_name = bot.user.name if bot.user else "NorthBears"
    draw.text((250, 150), f"🐻 {bot_name}", fill="white", font=font_title)
    draw.text((250, 210), title, fill="#FFFFFF", font=font_text)
    
    # Разбиваем длинный текст на строки
    lines = text.split('\n')
    y = 260
    for line in lines:
        draw.text((250, y), line, fill="#E8E8E8", font=font_text)
        y += 30
    
    draw.text((50, 400), "NorthBears Bot", fill="#FFFFFF", font=font_text)
    draw.text((650, 400), datetime.now().strftime("%d.%m.%Y %H:%M"), fill="#FFFFFF", font=font_text)
    
    img_buffer = BytesIO()
    img.save(img_buffer, format='PNG')
    img_buffer.seek(0)
    return img_buffer

async def send_with_image(interaction, title, description, color="#4A90D9", footer=None):
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

def is_master_admin(user):
    """Проверка, является ли пользователь главным администратором"""
    return user.name == MASTER_ADMIN or str(user) == MASTER_ADMIN

def is_admin(user):
    """Проверка, является ли пользователь администратором"""
    if is_master_admin(user):
        return True
    if str(user.id) in settings.get("admin_users", []):
        return True
    user_roles = [role.name for role in user.roles]
    return any(role in settings.get("admin_roles", []) for role in user_roles)

def is_moderator(user):
    """Проверка, является ли пользователь модератором"""
    if is_admin(user):
        return True
    if str(user.id) in settings.get("moderator_users", []):
        return True
    user_roles = [role.name for role in user.roles]
    return any(role in settings.get("moderator_roles", []) for role in user_roles)

def has_permission(interaction, required_roles):
    """Проверка прав на команду"""
    if is_master_admin(interaction.user):
        return True
    user_roles = [role.name for role in interaction.user.roles]
    return any(role in user_roles for role in required_roles)

# ============================================================
# ФУНКЦИЯ ДЛЯ ПОЛУЧЕНИЯ СПИСКА РОЛЕЙ И ПОЛЬЗОВАТЕЛЕЙ
# ============================================================

def get_roles_list(guild):
    """Возвращает список ролей для отображения"""
    roles = []
    for role in guild.roles:
        if role.name != "@everyone":
            roles.append(f"{role.name} (ID: {role.id})")
    return roles

def get_users_list(guild):
    """Возвращает список пользователей для отображения"""
    users = []
    for member in guild.members:
        users.append(f"{member.name}#{member.discriminator} (ID: {member.id})")
    return users

# ============================================================
# КЛАССЫ ДЛЯ ВЫБОРА ПОЛЬЗОВАТЕЛЕЙ И РОЛЕЙ
# ============================================================

class UserSelect(discord.ui.Select):
    def __init__(self, guild, action, role_type):
        self.guild = guild
        self.action = action
        self.role_type = role_type
        
        options = []
        for member in guild.members[:25]:  # Максимум 25 опций
            options.append(
                discord.SelectOption(
                    label=member.name[:100],
                    value=str(member.id),
                    description=f"#{member.discriminator}"
                )
            )
        
        super().__init__(
            placeholder="Выберите пользователя...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        user_id = self.values[0]
        member = self.guild.get_member(int(user_id))
        
        if not member:
            await interaction.response.send_message("❌ Пользователь не найден!", ephemeral=True)
            return
        
        if self.action == "add_admin":
            if str(member.id) in settings["admin_users"]:
                await interaction.response.send_message(f"❌ {member.mention} уже администратор!", ephemeral=True)
                return
            settings["admin_users"].append(str(member.id))
            save_settings(settings)
            await interaction.response.send_message(f"✅ {member.mention} добавлен в администраторы!", ephemeral=True)
        
        elif self.action == "remove_admin":
            if str(member.id) not in settings["admin_users"]:
                await interaction.response.send_message(f"❌ {member.mention} не является администратором!", ephemeral=True)
                return
            settings["admin_users"].remove(str(member.id))
            save_settings(settings)
            await interaction.response.send_message(f"✅ {member.mention} удален из администраторов!", ephemeral=True)
        
        elif self.action == "add_moderator":
            if str(member.id) in settings["moderator_users"]:
                await interaction.response.send_message(f"❌ {member.mention} уже модератор!", ephemeral=True)
                return
            settings["moderator_users"].append(str(member.id))
            save_settings(settings)
            await interaction.response.send_message(f"✅ {member.mention} добавлен в модераторы!", ephemeral=True)
        
        elif self.action == "remove_moderator":
            if str(member.id) not in settings["moderator_users"]:
                await interaction.response.send_message(f"❌ {member.mention} не является модератором!", ephemeral=True)
                return
            settings["moderator_users"].remove(str(member.id))
            save_settings(settings)
            await interaction.response.send_message(f"✅ {member.mention} удален из модераторов!", ephemeral=True)

class RoleSelect(discord.ui.Select):
    def __init__(self, guild, action, role_type):
        self.guild = guild
        self.action = action
        self.role_type = role_type
        
        options = []
        for role in guild.roles:
            if role.name != "@everyone":
                options.append(
                    discord.SelectOption(
                        label=role.name[:100],
                        value=role.name,
                        description=f"ID: {role.id}"
                    )
                )
                if len(options) >= 25:
                    break
        
        super().__init__(
            placeholder="Выберите роль...",
            min_values=1,
            max_values=1,
            options=options
        )
    
    async def callback(self, interaction: discord.Interaction):
        role_name = self.values[0]
        
        if self.action == "add_admin_role":
            if role_name in settings["admin_roles"]:
                await interaction.response.send_message(f"❌ Роль `{role_name}` уже в списке администраторов!", ephemeral=True)
                return
            settings["admin_roles"].append(role_name)
            save_settings(settings)
            await interaction.response.send_message(f"✅ Роль `{role_name}` добавлена в администраторы!", ephemeral=True)
        
        elif self.action == "remove_admin_role":
            if role_name not in settings["admin_roles"]:
                await interaction.response.send_message(f"❌ Роль `{role_name}` не в списке администраторов!", ephemeral=True)
                return
            settings["admin_roles"].remove(role_name)
            save_settings(settings)
            await interaction.response.send_message(f"✅ Роль `{role_name}` удалена из администраторов!", ephemeral=True)
        
        elif self.action == "add_moderator_role":
            if role_name in settings["moderator_roles"]:
                await interaction.response.send_message(f"❌ Роль `{role_name}` уже в списке модераторов!", ephemeral=True)
                return
            settings["moderator_roles"].append(role_name)
            save_settings(settings)
            await interaction.response.send_message(f"✅ Роль `{role_name}` добавлена в модераторы!", ephemeral=True)
        
        elif self.action == "remove_moderator_role":
            if role_name not in settings["moderator_roles"]:
                await interaction.response.send_message(f"❌ Роль `{role_name}` не в списке модераторов!", ephemeral=True)
                return
            settings["moderator_roles"].remove(role_name)
            save_settings(settings)
            await interaction.response.send_message(f"✅ Роль `{role_name}` удалена из модераторов!", ephemeral=True)

class ConfigView(discord.ui.View):
    def __init__(self, guild):
        super().__init__(timeout=300)
        self.guild = guild
        
        # Кнопки для управления
        self.add_item(discord.ui.Button(label="📋 Показать конфиг", style=discord.ButtonStyle.primary, custom_id="show_config"))
        self.add_item(discord.ui.Button(label="➕ Добавить админа", style=discord.ButtonStyle.success, custom_id="add_admin"))
        self.add_item(discord.ui.Button(label="➖ Удалить админа", style=discord.ButtonStyle.danger, custom_id="remove_admin"))
        self.add_item(discord.ui.Button(label="➕ Добавить модера", style=discord.ButtonStyle.success, custom_id="add_moderator"))
        self.add_item(discord.ui.Button(label="➖ Удалить модера", style=discord.ButtonStyle.danger, custom_id="remove_moderator"))
        self.add_item(discord.ui.Button(label="👥 Список участников", style=discord.ButtonStyle.secondary, custom_id="list_users"))
        self.add_item(discord.ui.Button(label="📜 Список ролей", style=discord.ButtonStyle.secondary, custom_id="list_roles"))
        self.add_item(discord.ui.Button(label="❌ Закрыть", style=discord.ButtonStyle.danger, custom_id="close"))

# ============================================================
# КОМАНДА /CONFIG
# ============================================================

@bot.tree.command(name="config", description="Управление настройками бота")
async def config(interaction: discord.Interaction):
    # Проверка: только главный администратор или администратор
    if not is_master_admin(interaction.user) and not is_admin(interaction.user):
        await interaction.response.send_message("❌ У вас нет прав на использование этой команды!", ephemeral=True)
        return
    
    # Создаем embed с управлением
    embed = discord.Embed(
        title="⚙️ Панель управления ботом",
        description="Используйте кнопки ниже для управления настройками",
        color=discord.Color.blue()
    )
    embed.add_field(
        name="👑 Главный администратор",
        value=f"**{MASTER_ADMIN}**",
        inline=False
    )
    embed.add_field(
        name="📋 Текущие настройки",
        value=f"**Администраторы:** {', '.join(settings['admin_roles'])}\n"
              f"**Модераторы:** {', '.join(settings['moderator_roles'])}\n"
              f"**Админы (пользователи):** {len(settings['admin_users'])} чел.\n"
              f"**Модеры (пользователи):** {len(settings['moderator_users'])} чел.",
        inline=False
    )
    embed.set_footer(text="Нажмите кнопку для действия")
    
    view = discord.ui.View(timeout=300)
    
    # Кнопка показа конфига
    async def show_config_callback(interaction: discord.Interaction):
        if not is_master_admin(interaction.user) and not is_admin(interaction.user):
            await interaction.response.send_message("❌ Нет прав!", ephemeral=True)
            return
        
        admin_users = []
        for uid in settings["admin_users"]:
            user = interaction.guild.get_member(int(uid))
            if user:
                admin_users.append(user.mention)
            else:
                admin_users.append(f"Unknown ({uid})")
        
        mod_users = []
        for uid in settings["moderator_users"]:
            user = interaction.guild.get_member(int(uid))
            if user:
                mod_users.append(user.mention)
            else:
                mod_users.append(f"Unknown ({uid})")
        
        text = f"""
**👑 Главный админ:** {MASTER_ADMIN}

**👔 Администраторы (роли):**
{', '.join(settings['admin_roles']) if settings['admin_roles'] else 'Нет'}

**🛡️ Администраторы (пользователи):**
{', '.join(admin_users) if admin_users else 'Нет'}

**👤 Модераторы (роли):**
{', '.join(settings['moderator_roles']) if settings['moderator_roles'] else 'Нет'}

**👥 Модераторы (пользователи):**
{', '.join(mod_users) if mod_users else 'Нет'}
"""
        await send_with_image(interaction, "📋 Полная конфигурация", text)
    
    # Кнопка добавления админа (пользователя)
    async def add_admin_callback(interaction: discord.Interaction):
        if not is_master_admin(interaction.user):
            await interaction.response.send_message("❌ Только главный администратор может это делать!", ephemeral=True)
            return
        
        view = discord.ui.View(timeout=60)
        select = UserSelect(interaction.guild, "add_admin", "admin")
        view.add_item(select)
        await interaction.response.send_message("Выберите пользователя для добавления в администраторы:", view=view, ephemeral=True)
    
    # Кнопка удаления админа
    async def remove_admin_callback(interaction: discord.Interaction):
        if not is_master_admin(interaction.user):
            await interaction.response.send_message("❌ Только главный администратор может это делать!", ephemeral=True)
            return
        
        if not settings["admin_users"]:
            await interaction.response.send_message("❌ Нет пользователей-администраторов для удаления!", ephemeral=True)
            return
        
        view = discord.ui.View(timeout=60)
        select = UserSelect(interaction.guild, "remove_admin", "admin")
        view.add_item(select)
        await interaction.response.send_message("Выберите пользователя для удаления из администраторов:", view=view, ephemeral=True)
    
    # Кнопка добавления модера
    async def add_moderator_callback(interaction: discord.Interaction):
        if not is_master_admin(interaction.user):
            await interaction.response.send_message("❌ Только главный администратор может это делать!", ephemeral=True)
            return
        
        view = discord.ui.View(timeout=60)
        select = UserSelect(interaction.guild, "add_moderator", "moderator")
        view.add_item(select)
        await interaction.response.send_message("Выберите пользователя для добавления в модераторы:", view=view, ephemeral=True)
    
    # Кнопка удаления модера
    async def remove_moderator_callback(interaction: discord.Interaction):
        if not is_master_admin(interaction.user):
            await interaction.response.send_message("❌ Только главный администратор может это делать!", ephemeral=True)
            return
        
        if not settings["moderator_users"]:
            await interaction.response.send_message("❌ Нет пользователей-модераторов для удаления!", ephemeral=True)
            return
        
        view = discord.ui.View(timeout=60)
        select = UserSelect(interaction.guild, "remove_moderator", "moderator")
        view.add_item(select)
        await interaction.response.send_message("Выберите пользователя для удаления из модераторов:", view=view, ephemeral=True)
    
    # Кнопка списка участников
    async def list_users_callback(interaction: discord.Interaction):
        if not is_master_admin(interaction.user) and not is_admin(interaction.user):
            await interaction.response.send_message("❌ Нет прав!", ephemeral=True)
            return
        
        users = get_users_list(interaction.guild)
        text = "**👥 Список участников сервера:**\n\n"
        for i, user in enumerate(users[:20], 1):
            text += f"{i}. {user}\n"
        if len(users) > 20:
            text += f"\n...и еще {len(users) - 20} участников"
        
        await send_with_image(interaction, "👥 Участники сервера", text)
    
    # Кнопка списка ролей
    async def list_roles_callback(interaction: discord.Interaction):
        if not is_master_admin(interaction.user) and not is_admin(interaction.user):
            await interaction.response.send_message("❌ Нет прав!", ephemeral=True)
            return
        
        roles = get_roles_list(interaction.guild)
        text = "**📜 Список ролей сервера:**\n\n"
        for i, role in enumerate(roles[:20], 1):
            text += f"{i}. {role}\n"
        if len(roles) > 20:
            text += f"\n...и еще {len(roles) - 20} ролей"
        
        await send_with_image(interaction, "📜 Роли сервера", text)
    
    # Закрыть
    async def close_callback(interaction: discord.Interaction):
        await interaction.response.send_message("✅ Панель закрыта", ephemeral=True)
    
    # Добавляем кнопки
    view.add_item(discord.ui.Button(label="📋 Показать конфиг", style=discord.ButtonStyle.primary, custom_id="show_config"))
    view.add_item(discord.ui.Button(label="➕ Добавить админа", style=discord.ButtonStyle.success, custom_id="add_admin"))
    view.add_item(discord.ui.Button(label="➖ Удалить админа", style=discord.ButtonStyle.danger, custom_id="remove_admin"))
    view.add_item(discord.ui.Button(label="➕ Добавить модера", style=discord.ButtonStyle.success, custom_id="add_moderator"))
    view.add_item(discord.ui.Button(label="➖ Удалить модера", style=discord.ButtonStyle.danger, custom_id="remove_moderator"))
    view.add_item(discord.ui.Button(label="👥 Список участников", style=discord.ButtonStyle.secondary, custom_id="list_users"))
    view.add_item(discord.ui.Button(label="📜 Список ролей", style=discord.ButtonStyle.secondary, custom_id="list_roles"))
    view.add_item(discord.ui.Button(label="❌ Закрыть", style=discord.ButtonStyle.danger, custom_id="close"))
    
    # Обработчики кнопок
    async def button_callback(interaction: discord.Interaction):
        custom_id = interaction.data.get("custom_id")
        
        if custom_id == "show_config":
            await show_config_callback(interaction)
        elif custom_id == "add_admin":
            await add_admin_callback(interaction)
        elif custom_id == "remove_admin":
            await remove_admin_callback(interaction)
        elif custom_id == "add_moderator":
            await add_moderator_callback(interaction)
        elif custom_id == "remove_moderator":
            await remove_moderator_callback(interaction)
        elif custom_id == "list_users":
            await list_users_callback(interaction)
        elif custom_id == "list_roles":
            await list_roles_callback(interaction)
        elif custom_id == "close":
            await close_callback(interaction)
    
    for item in view.children:
        if isinstance(item, discord.ui.Button):
            item.callback = button_callback
    
    await interaction.response.send_message(embed=embed, view=view)

# ============================================================
# ОСТАЛЬНЫЕ КОМАНДЫ (KICK, MUTE, BAN, UNMUTE, HELP)
# ============================================================

@bot.tree.command(name="kick", description="Выгнать пользователя с сервера")
@app_commands.describe(member="Пользователь для кика", reason="Причина кика")
async def kick(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    if not has_permission(interaction, settings.get("kick_roles", [])) and not is_moderator(interaction.user):
        await interaction.response.send_message("❌ У вас нет прав на использование этой команды!", ephemeral=True)
        return
    
    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner and not is_master_admin(interaction.user):
        await interaction.response.send_message("❌ Вы не можете выгнать этого пользователя!", ephemeral=True)
        return
    
    try:
        await member.kick(reason=f"{interaction.user.name}: {reason}")
        await send_with_image(interaction, "👢 Пользователь кикнут", f"{member.mention} был кикнут!\n👤 Модератор: {interaction.user.mention}\n📝 Причина: {reason}")
    except discord.Forbidden:
        await interaction.response.send_message("❌ У меня недостаточно прав!", ephemeral=True)

@bot.tree.command(name="mute", description="Замьютить пользователя")
@app_commands.describe(member="Пользователь для мута", duration="Длительность (1h, 30m, 45s)", reason="Причина мута")
async def mute(interaction: discord.Interaction, member: discord.Member, duration: str, reason: str = "Не указана"):
    if not has_permission(interaction, settings.get("mute_roles", [])) and not is_moderator(interaction.user):
        await interaction.response.send_message("❌ У вас нет прав на использование этой команды!", ephemeral=True)
        return
    
    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner and not is_master_admin(interaction.user):
        await interaction.response.send_message("❌ Вы не можете замьютить этого пользователя!", ephemeral=True)
        return
    
    try:
        total_seconds = parse_duration(duration)
        if total_seconds <= 0:
            await interaction.response.send_message("❌ Неверный формат! Пример: 1h30m", ephemeral=True)
            return
        duration_delta = timedelta(seconds=total_seconds)
    except:
        await interaction.response.send_message("❌ Неверный формат! Пример: 1h30m", ephemeral=True)
        return
    
    view = MuteView(member, duration_delta, reason, interaction.user)
    embed = discord.Embed(title="⚠️ Подтверждение мута", description=f"Вы уверены, что хотите замьютить {member.mention}?", color=discord.Color.yellow())
    embed.add_field(name="⏱️ Длительность", value=duration, inline=True)
    embed.add_field(name="📝 Причина", value=reason, inline=False)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="ban", description="Забанить пользователя")
@app_commands.describe(member="Пользователь для бана", reason="Причина бана", delete_messages="Удалить сообщения (дни)")
async def ban(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана", delete_messages: int = 0):
    if not has_permission(interaction, settings.get("ban_roles", [])) and not is_admin(interaction.user):
        await interaction.response.send_message("❌ У вас нет прав на использование этой команды!", ephemeral=True)
        return
    
    if member.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner and not is_master_admin(interaction.user):
        await interaction.response.send_message("❌ Вы не можете забанить этого пользователя!", ephemeral=True)
        return
    
    view = BanView(member, reason, interaction.user, delete_messages)
    embed = discord.Embed(title="⚠️ Подтверждение бана", description=f"Вы уверены, что хотите забанить {member.mention}?", color=discord.Color.yellow())
    embed.add_field(name="📝 Причина", value=reason, inline=False)
    embed.add_field(name="🗑️ Удалить сообщения за", value=f"{delete_messages} дней", inline=False)
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name="unmute", description="Снять мут с пользователя")
@app_commands.describe(member="Пользователь для размута", reason="Причина размута")
async def unmute(interaction: discord.Interaction, member: discord.Member, reason: str = "Не указана"):
    if not has_permission(interaction, settings.get("mute_roles", [])) and not is_moderator(interaction.user):
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
        await send_with_image(interaction, "🔊 Пользователь размьючен", f"{member.mention} был размьючен!\n👤 Модератор: {interaction.user.mention}\n📝 Причина: {reason}")
    except discord.Forbidden:
        await interaction.response.send_message("❌ У меня недостаточно прав!", ephemeral=True)

@bot.tree.command(name="help", description="Показать список команд")
async def help_command(interaction: discord.Interaction):
    help_text = """
**📚 Команды бота:**

👢 `/kick @пользователь причина` - Выгнать пользователя
🔇 `/mute @пользователь 1h30m причина` - Замьютить
🔊 `/unmute @пользователь причина` - Снять мут
🔨 `/ban @пользователь причина дни` - Забанить
⚙️ `/config` - Панель управления (админы)
📖 `/help` - Эта помощь

**Форматы длительности:** 1h, 30m, 45s, 1h30m45s
"""
    await send_with_image(interaction, "📚 Помощь по командам", help_text)

# ============================================================
# КЛАССЫ ДЛЯ КНОПОК ПОДТВЕРЖДЕНИЯ
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
        
        await send_with_image(interaction, "🔇 Пользователь замьючен", f"{self.member.mention} был замьючен!\n⏱️ Длительность: {str(self.duration)}\n👤 Модератор: {interaction.user.mention}\n📝 Причина: {self.reason}\n⏰ Размут в: {unmute_time.strftime('%d.%m.%Y %H:%M:%S')}")
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
            await send_with_image(interaction, "🔨 Пользователь забанен", f"{self.member.mention} был забанен!\n👤 Модератор: {interaction.user.mention}\n📝 Причина: {self.reason}\n🗑️ Удалено сообщений за: {self.delete_days} дней")
        except discord.Forbidden:
            await interaction.response.send_message("❌ У меня недостаточно прав!", ephemeral=True)
        
        self.stop()

    @discord.ui.button(label="❌ Отмена", style=discord.ButtonStyle.secondary)
    async def cancel_ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.moderator:
            await interaction.response.send_message("❌ Вы не можете использовать эту кнопку!", ephemeral=True)
            return
        await interaction.response.send_message("✅ Бан отменен!", ephemeral=True)
        self.stop()

# ============================================================
# ПАРСИНГ ДЛИТЕЛЬНОСТИ И ПРОВЕРКА МУТОВ
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

@bot.event
async def on_ready():
    print(f'✅ Бот {bot.user.name} готов к работе!')
    print(f'📊 На серверах: {len(bot.guilds)}')
    print(f'👑 Главный администратор: {MASTER_ADMIN}')
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
            del muted_users[user_id]
        await asyncio.sleep(60)

# ============================================================
# ЗАПУСК
# ============================================================

if __name__ == "__main__":
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        print("❌ Токен не найден! Проверьте переменную DISCORD_TOKEN")
    else:
        bot.run(token)
