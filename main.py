import discord
from discord.ext import commands
from discord import app_commands  # Новый модуль для слэш-команд
import sqlite3
import random
import time

intents = discord.Intents.default()
intents.message_content = True  
intents.members = True          
bot = commands.Bot(command_prefix="!", intents=intents)

# Подключение базы данных SQLite
conn = sqlite3.connect("levels.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER,
    guild_id INTEGER,
    xp INTEGER DEFAULT 0,
    level INTEGER DEFAULT 1,
    last_msg REAL DEFAULT 0,
    PRIMARY KEY (user_id, guild_id)
)
""")
conn.commit()

@bot.event
async def on_ready():
    print(f"Робот {bot.user.name} запущен!")
    try:
        # Синхронизируем команды с серверами Discord (это выведет их в меню)
        synced = await bot.tree.sync()
        print(f"Успешно синхронизировано слэш-команд: {len(synced)}")
    except Exception as e:
        print(f"Ошибка синхронизации: {e}")

# Фоновое начисление опыта за сообщения остается прежним
@bot.event
async def on_message(message):
    if message.author.bot or not message.guild:
        return

    user_id = message.author.id
    guild_id = message.guild.id
    current_time = time.time()

    cursor.execute("SELECT xp, level, last_msg FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    result = cursor.fetchone()

    if result is None:
        cursor.execute("INSERT INTO users (user_id, guild_id, last_msg) VALUES (?, ?, ?)", (user_id, guild_id, current_time))
        conn.commit()
        result = (0, 1, current_time)

    xp, level, last_msg = result

    if True: # Опыт идет за каждое сообщение, счетчик ниже

        # Используем поле last_msg для подсчета сообщений (назовем его msg_count для удобства)
        msg_count = int(last_msg) + 1

        if msg_count >= 10: # Ровно каждые 10 сообщений
            xp_to_add = random.randint(15, 25)
            new_xp = xp + xp_to_add
            xp_needed = 5 * (level ** 2) + 50 * level + 100

            if new_xp >= xp_needed:
                level += 1
                new_xp = new_xp - xp_needed
                await message.channel.send(f"🎉 {message.author.mention}, вы достигли нового уровня: **{level}**!")
    
            cursor.execute("UPDATE users SET xp = ?, level = ?, last_msg = 0 WHERE user_id = ? AND guild_id = ?", 
                   (new_xp, level, user_id, guild_id))
        else:
            cursor.execute("UPDATE users SET last_msg = ? WHERE user_id = ? AND guild_id = ?", 
                   (msg_count, user_id, guild_id))
        conn.commit()


    await bot.process_commands(message)

# --- НОВАЯ СЛЭШ-КОМАНДА ДЛЯ МЕНЮ ---
@bot.tree.command(name="ранг", description="Посмотреть уровень и опыт участника")
@app_commands.describe(участник="Выберите участника, чей ранг хотите посмотреть (необязательно)")
async def rank_slash(interaction: discord.Interaction, участник: discord.Member = None):
    # В слэш-командах вместо ctx используется interaction
    member = участник or interaction.user 
    
    cursor.execute("SELECT xp, level FROM users WHERE user_id = ? AND guild_id = ?", (member.id, interaction.guild.id))
    result = cursor.fetchone()

    if result is None:
        xp, level = 0, 1
    else:
        xp, level = result

    xp_needed = 5 * (level ** 2) + 50 * level + 100

    embed = discord.Embed(title=f"Рейтинг участника {member.display_name}", color=0x3498db)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.add_field(name="Уровень", value=f"⭐ **{level}**", inline=True)
    embed.add_field(name="Опыт (XP)", value=f"📊 **{xp}/{xp_needed}**", inline=True)
    
    progress = int((xp / xp_needed) * 10)
    bar = "🟩" * progress + "⬛" * (10 - progress)
    embed.add_field(name="Прогресс", value=bar, inline=False)

    # В слэш-командах вместо ctx.send используется interaction.response.send_message
    await interaction.response.send_message(embed=embed)

# --- АДМИНИСТРАТИВНАЯ СЛЭШ-КОМАНДА ДЛЯ ИЗМЕНЕНИЯ УРОВНЯ ---
@bot.tree.command(name="уровень_установить", description="[Админ] Установить уровень конкретному участнику")
@app_commands.describe(
    участник="Выберите пользователя",
    уровень="Укажите новый уровень (число)"
)
@app_commands.checks.has_permissions(administrator=True) # Доступ только для Администраторов
async def set_level(interaction: discord.Interaction, участник: discord.Member, уровень: int):
    if уровень < 1:
        await interaction.response.send_message("❌ Уровень не может быть меньше 1!", ephemeral=True)
        return

    user_id = участник.id
    guild_id = interaction.guild.id

    # Сбрасываем XP на 0 для нового уровня, чтобы прогресс начался заново
    new_xp = 0

    # Проверяем, есть ли уже пользователь в базе данных
    cursor.execute("SELECT level FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    result = cursor.fetchone()

    if result is None:
        # Если пользователя не было в базе, создаем запись
        cursor.execute("INSERT INTO users (user_id, guild_id, xp, level, last_msg) VALUES (?, ?, ?, ?, ?)", 
                       (user_id, guild_id, new_xp, уровень, 0))
    else:
        # Если был — обновляем его данные
        cursor.execute("UPDATE users SET xp = ?, level = ? WHERE user_id = ? AND guild_id = ?", 
                       (new_xp, уровень, user_id, guild_id))
    
    conn.commit()

    await interaction.response.send_message(
        f"✅ Уровень участника {участник.mention} успешно изменен на **{уровень}**!", 
        ephemeral=False # Сообщение увидят все в чате как подтверждение
    )

# Обработка ошибки, если команду попытается прописать не админ
@set_level.error
async def set_level_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message(
            "❌ У вас недостаточно прав для использования этой команды! Требуются права Администратора.", 
            ephemeral=True # Ошибку увидит только нарушитель
        )


# --- СЛЭШ-КОМАНДА: ТАБЛИЦА ЛИДЕРОВ (/топ) ---
@bot.tree.command(name="топ", description="Показать топ-10 самых активных участников сервера")
async def leaderboard(interaction: discord.Interaction):
    # Сортируем пользователей сначала по уровню, затем по опыту (XP)
    cursor.execute("""
        SELECT user_id, level, xp FROM users 
        WHERE guild_id = ? 
        ORDER BY level DESC, xp DESC 
        LIMIT 10
    """, (interaction.guild.id,))
    
    rows = cursor.fetchall()
    
    if not rows:
        await interaction.response.send_message("📭 Таблица лидеров пока пуста. Начните общаться!", ephemeral=True)
        return

    embed = discord.Embed(title=f"🏆 Таблица лидеров {interaction.guild.name}", color=0xe74c3c)
    
    description_text = ""
    medals = ["🥇", "🥈", "🥉"] # Медали для первых трех мест
    
    for index, row in enumerate(rows):
        user_id, level, xp = row
        member = interaction.guild.get_member(user_id)
        
        # Если участник вышел с сервера, пишем "Покинул сервер"
        name = member.display_name if member else f"Участник ({user_id})"
        
        prefix = medals[index] if index < 3 else f"`#{index + 1}`"
        description_text += f"{prefix} **{name}** — Уровень: **{level}** (XP: {xp})\n"

    embed.description = description_text
    await interaction.response.send_message(embed=embed)


# --- СЛЭШ-КОМАНДА: ДОБАВЛЕНИЕ ОПЫТА (/опыт_добавить) ---
@bot.tree.command(name="опыт_добавить", description="[Админ] Добавить или отнять опыт у участника")
@app_commands.describe(
    участник="Выберите пользователя",
    количество="Сколько XP добавить (можно указать минус, чтобы отнять)"
)
@app_commands.checks.has_permissions(administrator=True) # Доступ только для Администраторов
async def add_xp(interaction: discord.Interaction, участник: discord.Member, количество: int):
    user_id = участник.id
    guild_id = interaction.guild.id

    cursor.execute("SELECT xp, level FROM users WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    result = cursor.fetchone()

    if result is None:
        xp, level = 0, 1
        cursor.execute("INSERT INTO users (user_id, guild_id, xp, level, last_msg) VALUES (?, ?, ?, ?, 0)", 
                       (user_id, guild_id, xp, level))
    else:
        xp, level = result

    # Считаем новый опыт
    new_xp = xp + количество
    
    # Если ушли в минус по опыту
    if new_xp < 0:
        new_xp = 0

    # Проверяем, повысился ли уровень от добавления опыта
    xp_needed = 5 * (level ** 2) + 50 * level + 100
    leveled_up = False

    while new_xp >= xp_needed:
        level += 1
        new_xp -= xp_needed
        xp_needed = 5 * (level ** 2) + 50 * level + 100
        leveled_up = True

    cursor.execute("UPDATE users SET xp = ?, level = ? WHERE user_id = ? AND guild_id = ?", 
                   (new_xp, level, user_id, guild_id))
    conn.commit()

    response_text = f"✅ Участнику {участник.mention} успешно начислено **{количество} XP**!"
    if leveled_up:
        response_text += f"\n🎉 Новый уровень пользователя: **{level}**!"

    await interaction.response.send_message(response_text)

# Обработка ошибки прав для команды /опыт_добавить
@add_xp.error
async def add_xp_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ Ошибка: Нужны права Администратора.", ephemeral=True)

# --- СЛЭШ-КОМАНДА: ОЧИСТКА ЧАТА (/очистить) ---
@bot.tree.command(name="очистить", description="[Модерация] Удалить указанное количество сообщений из чата")
@app_commands.describe(количество="Сколько сообщений нужно удалить (от 1 до 100)")
@app_commands.checks.has_permissions(manage_messages=True) # Доступ только для тех, кто может управлять сообщениями
async def clear_messages(interaction: discord.Interaction, количество: int):
    # Ограничиваем ввод логическими рамками (нельзя удалить меньше 1 или слишком много за раз)
    if количество < 1 or количество > 100:
        await interaction.response.send_message("❌ Можно удалить только от 1 до 100 сообщений за один раз!", ephemeral=True)
        return

    # Сначала отвечаем Discord, чтобы команда не «упала» по таймауту во время удаления
    await interaction.response.send_message(f"⏳ Начинаю очистку сообщений ({количество})...", ephemeral=True)

    # Удаляем сообщения (метод purge автоматически игнорирует сообщения старше 14 дней из-за ограничений Discord API)
    deleted = await interaction.channel.purge(limit=количество)

    # Обновляем наше скрытое сообщение, показывая финальный результат
    await interaction.edit_original_response(content=f"✅ Успешно удалено сообщений: **{len(deleted)}**.")

# Обработка ошибки, если команду попытается прописать участник без прав модератора
@clear_messages.error
async def clear_messages_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message(
            "❌ У вас недостаточно прав для очистки чата! Требуется разрешение «Управлять сообщениями».", 
            ephemeral=True
        )


# Сюда вставьте ваш токен из Discord Developer Portal
import os
bot.run(os.getenv("BOT_TOKEN"))

