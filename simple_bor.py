import telebot
from telebot import types
import json
import os
from typing import Dict, Any, Optional
import asyncio
import aiohttp
from dotenv import load_dotenv
import threading


# Загрузка токена из .env
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_CODE = os.getenv('ADMIN_CODE', 'admin123')  # Код по умолчанию, если не указан в .env

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Структура для хранения данных
DATA_FILE = 'bot_data.json'

def load_data() -> Dict[str, Any]:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            try:
                data = json.load(f)
                # Проверка наличия обязательных полей
                if 'results' not in data:
                    data['results'] = {}
                return data
            except json.JSONDecodeError:
                print("Ошибка: Невозможно декодировать JSON. Создаю новый файл данных.")
                return {
                    'users': {},
                    'classes': {},
                    'tests': {},
                    'results': {}
                }
    return {
        'users': {},
        'classes': {},
        'tests': {},
        'results': {}
    }

def save_data(data: Dict[str, Any]):
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# Хранение состояний пользователей
user_states = {}

def run_async(coro):
    """Запускает асинхронную корутину в отдельном потоке."""
    def wrapper():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(coro)
    threading.Thread(target=wrapper).start()

@bot.message_handler(commands=['start'])
def start(message):
    data = load_data()
    user_id = str(message.from_user.id)
    if user_id not in data['users']:
        markup = types.InlineKeyboardMarkup()
        teacher_button = types.InlineKeyboardButton("Я учитель", callback_data='register_teacher')
        student_button = types.InlineKeyboardButton("Я ученик", callback_data='register_student')
        markup.add(teacher_button, student_button)
        bot.reply_to(message, 
                     f"Добро пожаловать, {message.from_user.first_name}! Пожалуйста, выберите вашу роль:",
                     reply_markup=markup)
    else:
        role = "учителя" if data['users'][user_id]['role'] == 'teacher' else "ученика"
        show_main_menu(user_id, message)

def show_main_menu(user_id, message):
    data = load_data()
    role = data['users'][user_id]['role']
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    
    if role == 'teacher':
        # Кнопки только для учителя
        markup.add(types.KeyboardButton("Создать класс"))
        markup.add(types.KeyboardButton("Создать тест"))
        markup.add(types.KeyboardButton("Просмотреть тесты"))
        markup.add(types.KeyboardButton("Назначить тест"))
        markup.add(types.KeyboardButton("Просмотреть результаты"))
    elif role == 'student':
        # Кнопки только для ученика
        markup.add(types.KeyboardButton("Мои тесты"))
        markup.add(types.KeyboardButton("Мои результаты"))
    
    bot.reply_to(message, "Выберите действие:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    user_id = str(call.from_user.id)
    if call.data == 'register_teacher':
        user_states[user_id] = {'registering': 'teacher'}
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Пожалуйста, введите код администратора для регистрации учителя:"
        )
    elif call.data == 'register_student':
        user_states[user_id] = {'registering': 'student'}
        bot.edit_message_text(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            text="Пожалуйста, введите код доступа к классу, предоставленный учителем:"
        )

@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id), {}).get('registering') == 'student')
def handle_student_registration(message):
    user_id = str(message.from_user.id)
    entered_code = message.text.strip()
    data = load_data()
    class_found = False
    for class_id, class_info in data['classes'].items():
        if class_info.get('access_code') == entered_code:
            class_found = True
            if user_id not in data['users']:
                data['users'][user_id] = {
                    'role': 'student',
                    'username': message.from_user.first_name,
                    'class_id': class_id
                }
                class_info['students'].append(user_id)
                save_data(data)
                bot.reply_to(message, f"Вы успешно присоединились к классу '{class_info['name']}'!")
            else:
                bot.reply_to(message, "Вы уже зарегистрированы.")
            break
    if not class_found:
        bot.reply_to(message, "Неверный код доступа. Попробуйте снова или свяжитесь с учителем.")
    if user_id in user_states:
        del user_states[user_id]

@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id), {}).get('registering') == 'teacher')
def handle_teacher_registration(message):
    user_id = str(message.from_user.id)
    entered_code = message.text.strip()
    if entered_code == ADMIN_CODE:
        data = load_data()
        if user_id not in data['users']:
            data['users'][user_id] = {
                'role': 'teacher',
                'username': message.from_user.first_name
            }
            save_data(data)
            bot.reply_to(message, "Вы успешно зарегистрированы как учитель!")
        else:
            bot.reply_to(message, "Вы уже зарегистрированы.")
    else:
        bot.reply_to(message, "Неверный код администратора. Попробуйте снова или свяжитесь с администратором.")
    if user_id in user_states:
        del user_states[user_id]

@bot.message_handler(func=lambda message: message.text == "Создать класс")
def create_class(message):
    data = load_data()
    user_id = str(message.from_user.id)
    if user_id not in data['users'] or data['users'][user_id]['role'] != 'teacher':
        bot.reply_to(message, "Эта команда доступна только для учителей.")
        return
    user_states[user_id] = {'creating_class': True}
    bot.reply_to(message, "Введите название класса (например, '7A-2023'):")

@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id), {}).get('creating_class'))
def handle_create_class(message):
    user_id = str(message.from_user.id)
    class_name = message.text.strip()
    if len(class_name) < 3:
        bot.reply_to(message, "Название класса слишком короткое. Попробуйте снова:")
        return
    data = load_data()
    class_id = str(len(data['classes']) + 1)
    import random
    import string
    access_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    data['classes'][class_id] = {
        'id': class_id,
        'name': class_name,
        'teacher_id': user_id,
        'students': [],
        'access_code': access_code
    }
    save_data(data)
    del user_states[user_id]['creating_class']
    bot.reply_to(message, f"Класс '{class_name}' успешно создан!\nID класса: {class_id}\nКод доступа: {access_code}")

@bot.message_handler(func=lambda message: message.text == "Создать тест")
def handle_create_test(message):
    data = load_data()
    user_id = str(message.from_user.id)
    if data['users'].get(user_id, {}).get('role') != 'teacher':
        bot.reply_to(message, "Эта команда доступна только для учителей.")
        return
    user_states[user_id] = {'creating_test': {'step': 1}}
    bot.reply_to(message, "Введите тему теста:")


@bot.message_handler(func=lambda message: message.text == "Просмотреть результаты")
def handle_view_results(message):
    data = load_data()
    user_id = str(message.from_user.id)
    
    if data['users'].get(user_id, {}).get('role') != 'teacher':
        bot.reply_to(message, "🚫 Эта команда доступна только учителям")
        return

    teacher_classes = [c for c in data['classes'].values() if c['teacher_id'] == user_id]
    if not teacher_classes:
        bot.reply_to(message, "У вас нет созданных классов.")
        return
    
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True, row_width=2)
    for class_info in teacher_classes:
        btn = types.KeyboardButton(f"Класс: {class_info['name']}")
        markup.add(btn)
    markup.add(types.KeyboardButton("❌ Отмена"))
    
    user_states[user_id] = {'viewing_results': {'step': 1}}
    bot.reply_to(message, "Выберите класс для просмотра результатов:", reply_markup=markup)

@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id), {}).get('viewing_results'))
def handle_view_results_message(message):
    data = load_data()
    user_id = str(message.from_user.id)
    state = user_states.get(user_id, {})
    if 'viewing_results' in state:
        handle_view_results_logic(message, state, user_id, data)

@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id), {}).get('creating_test'))
def handle_creating_test(message):
    user_id = str(message.from_user.id)
    state = user_states[user_id]['creating_test']
    step = state['step']
    if step == 1:
        state['topic'] = message.text
        state['step'] = 2
        bot.reply_to(message, "Введите количество вопросов (например, 5):")
    elif step == 2:
        try:
            num_questions = int(message.text)
            if num_questions < 1 or num_questions > 20:
                raise ValueError()
            state['num_questions'] = num_questions
            state['step'] = 3
            bot.reply_to(message, "Выберите уровень сложности (легкий, средний, сложный):")
        except ValueError:
            bot.reply_to(message, "Неверное значение. Введите число от 1 до 20.")
    elif step == 3:
        difficulty = message.text.lower()
        if difficulty not in ['легкий', 'средний', 'сложный']:
            bot.reply_to(message, "Неверный уровень сложности. Выберите из: легкий, средний, сложный.")
            return
        state['difficulty'] = difficulty
        run_async(finalize_test_creation(
            user_id=user_id,
            topic=state['topic'],
            num_questions=state['num_questions'],
            difficulty=state['difficulty'],
            chat_id=message.chat.id
        ))
        del user_states[user_id]['creating_test']

def handle_view_results_logic(message, state, user_id, data):
    vr_state = state['viewing_results']
    step = vr_state['step']
    try:
        if step == 1:
            class_name = message.text.replace("Класс: ", "").strip()
            
            # Находим класс
            selected_class = next(
                (c for c in data['classes'].values() 
                 if c['name'] == class_name and c['teacher_id'] == user_id),
                None
            )
            
            if not selected_class:
                bot.reply_to(message, "Класс не найден. Попробуйте снова.")
                return

            # Получаем студентов класса (исправлено)
            students = [(uid, u) for uid, u in data['users'].items() 
                       if u.get('class_id') == selected_class['id']]
            
            if not students:
                bot.reply_to(message, f"В классе '{class_name}' пока нет учеников.", 
                           reply_markup=types.ReplyKeyboardRemove())
                del user_states[user_id]['viewing_results']
                return

            # Формируем отчет
            response = [f"📊 Результаты класса '{class_name}':\n"]
            for student_id, student in students:  # Исправлено здесь
                student_results = [
                    r for r in data['results'].values() 
                    if r['student_id'] == student_id  # Используем настоящий ID студента
                ]

                response.append(f"\n👤 {student['username']}:")
                if not student_results:
                    response.append(" Нет результатов")
                    continue

                for result in student_results:
                    test = data['tests'].get(result['test_id'], {})
                    response.append(
                        f"\n📝 Тест: {test.get('topic', 'Неизвестно')} "
                        f"(ID: {result['test_id']})"
                    )
                    response.append(
                        f"✅ Правильно: {result['correct_answers']}/{result['total_questions']}"
                    )
                    
                    if result.get('wrong_answers'):
                        response.append("\n❌ Ошибки:")
                        for idx, error in enumerate(result['wrong_answers'], 1):
                            response.append(
                                f"{idx}. Вопрос: {error['question']}\n"
                                f"   Ваш ответ: {error['user_answer']}\n"
                                f"   Правильный: {error['correct_answer']}"
                            )

            # Отправляем результаты частями
            full_response = "\n".join(response)
            for part in [full_response[i:i+4096] for i in range(0, len(full_response), 4096)]:
                bot.send_message(message.chat.id, part)

            del user_states[user_id]['viewing_results']

    except Exception as e:
        bot.reply_to(message, f"⚠️ Ошибка: {str(e)}")
        if user_id in user_states and 'viewing_results' in user_states[user_id]:
            del user_states[user_id]['viewing_results']

@bot.message_handler(func=lambda message: message.text == "❌ Отмена")
def cancel_operation(message):
    user_id = str(message.from_user.id)
    if user_id in user_states:
        del user_states[user_id]
    bot.reply_to(message, "Операция отменена", reply_markup=types.ReplyKeyboardRemove())


@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id), {}).get('assigning_test'))
def handle_assign_test_message(message):
    data = load_data()
    user_id = str(message.from_user.id)
    state = user_states.get(user_id, {})
    if 'assigning_test' in state:
        handle_assign_test(message, state, user_id, data)

def handle_assign_test(message, state, user_id, data):
    ct_state = state['assigning_test']
    step = ct_state['step']
    try:
        if step == 1:
            parts = message.text.split("ID: ")
            if len(parts) != 2:
                bot.reply_to(message, "Неверный формат теста. Попробуйте снова.")
                return
            test_id = parts[1].split(" - ")[0].strip()
            if test_id not in data['tests']:
                bot.reply_to(message, "Тест не найден. Попробуйте снова.")
                return
            ct_state['test_id'] = test_id
            ct_state['step'] = 2
            classes = [c for c in data['classes'].values() if c['teacher_id'] == user_id]
            if not classes:
                bot.reply_to(message, "У вас нет созданных классов.")
                return
            markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
            for class_info in classes:
                markup.add(types.KeyboardButton(f"Класс: {class_info['name']}"))
            bot.reply_to(message, "Выберите класс для назначения теста:", reply_markup=markup)
        elif step == 2:
            parts = message.text.split("Класс: ")
            if len(parts) != 2:
                bot.reply_to(message, "Неверный формат класса. Попробуйте снова.")
                return
            class_name = parts[1].strip()
            class_found = False
            for class_id, class_info in data['classes'].items():
                if class_info['name'] == class_name and class_info['teacher_id'] == user_id:
                    class_found = True
                    data['tests'][ct_state['test_id']]['class_id'] = class_id
                    save_data(data)
                    break
            if not class_found:
                bot.reply_to(message, "Класс не найден. Попробуйте снова.")
                return
            bot.reply_to(message, f"Тест ID: {ct_state['test_id']} успешно назначен классу {class_name}.",
                         reply_markup=types.ReplyKeyboardRemove())
            del user_states[user_id]['assigning_test']
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {str(e)}")
        if 'assigning_test' in user_states[user_id]:
            del user_states[user_id]['assigning_test']

@bot.message_handler(func=lambda message: message.text == "Мои тесты")
def my_tests(message):
    data = load_data()
    user_id = str(message.from_user.id)
    if user_id not in data['users'] or data['users'][user_id]['role'] != 'student':
        bot.reply_to(message, "Эта команда доступна только для учеников.")  
        return
    class_id = data['users'][user_id].get('class_id')
    if not class_id:
        bot.reply_to(message, "Вы не присоединены ни к одному классу.")
        return
    tests = [t for t in data['tests'].values() if t['class_id'] == class_id]
    if not tests:
        bot.reply_to(message, "У вас нет назначенных тестов.")
        return
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    for test in tests:
        markup.add(types.KeyboardButton(f"Тест ID: {test['id']} - {test['topic']}"))
    user_states[user_id] = {'taking_test': {'step': 1}}
    bot.reply_to(message, "Выберите тест для прохождения:", reply_markup=markup)

@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id), {}).get('taking_test'))
def handle_taking_test_message(message):
    data = load_data()
    user_id = str(message.from_user.id)
    state = user_states.get(user_id, {})
    if 'taking_test' in state:
        handle_taking_test(message, state, user_id, data)


@bot.message_handler(func=lambda message: message.text == "Просмотреть тесты")
def handle_view_tests(message):
    data = load_data()
    user_id = str(message.from_user.id)
    if data['users'].get(user_id, {}).get('role') != 'teacher':
        bot.reply_to(message, "🚫 Эта команда доступна только учителям")
        return

    teacher_tests = [t for t in data['tests'].values() if t['teacher_id'] == user_id]
    if not teacher_tests:
        bot.reply_to(message, "📭 У вас пока нет созданных тестов.")
        return

    response = ["📚 Список ваших тестов:\n"]
    for test in teacher_tests:
        class_info = data['classes'].get(test.get('class_id', ''), {})
        response.append(
            f"🔹 ID: {test['id']}\n"
            f"Тема: {test['topic']}\n"
            f"Сложность: {test['difficulty']}\n"
            f"Вопросов: {len(test['questions'])}\n"
            f"Класс: {class_info.get('name', 'Не назначен')}\n"
            "--------------------------"
        )
    
    full_response = "\n".join(response)
    for part in [full_response[i:i+4096] for i in range(0, len(full_response), 4096)]:
        bot.send_message(message.chat.id, part)

@bot.message_handler(func=lambda message: message.text == "Назначить тест")
def assign_test(message):
    data = load_data()
    user_id = str(message.from_user.id)
    if user_id not in data['users'] or data['users'][user_id]['role'] != 'teacher':
        bot.reply_to(message, "Эта команда доступна только для учителей.")
        return
    tests = [t for t in data['tests'].values() if t['teacher_id'] == user_id]
    if not tests:
        bot.reply_to(message, "У вас пока нет созданных тестов.")
        return
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    for test in tests:
        markup.add(types.KeyboardButton(f"Тест ID: {test['id']} - {test['topic']}"))
    user_states[user_id] = {'assigning_test': {'step': 1}}
    bot.reply_to(message, "Выберите тест для назначения:", reply_markup=markup)

@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id), {}).get('assigning_test'))
def handle_assign_test_message(message):
    data = load_data()
    user_id = str(message.from_user.id)
    state = user_states.get(user_id, {})
    if 'assigning_test' in state:
        handle_assign_test(message, state, user_id, data)

def handle_assign_test(message, state, user_id, data):
    ct_state = state['assigning_test']
    step = ct_state['step']
    try:
        if step == 1:
            parts = message.text.split("ID: ")
            if len(parts) != 2:
                bot.reply_to(message, "Неверный формат теста. Попробуйте снова.")
                return
            test_id = parts[1].split(" - ")[0].strip()
            if test_id not in data['tests']:
                bot.reply_to(message, "Тест не найден. Попробуйте снова.")
                return
            ct_state['test_id'] = test_id
            ct_state['step'] = 2
            classes = [c for c in data['classes'].values() if c['teacher_id'] == user_id]
            if not classes:
                bot.reply_to(message, "У вас нет созданных классов.")
                return
            markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
            for class_info in classes:
                markup.add(types.KeyboardButton(f"Класс: {class_info['name']}"))
            bot.reply_to(message, "Выберите класс для назначения теста:", reply_markup=markup)
        elif step == 2:
            parts = message.text.split("Класс: ")
            if len(parts) != 2:
                bot.reply_to(message, "Неверный формат класса. Попробуйте снова.")
                return
            class_name = parts[1].strip()
            class_found = False
            for class_id, class_info in data['classes'].items():
                if class_info['name'] == class_name and class_info['teacher_id'] == user_id:
                    class_found = True
                    data['tests'][ct_state['test_id']]['class_id'] = class_id
                    save_data(data)
                    break
            if not class_found:
                bot.reply_to(message, "Класс не найден. Попробуйте снова.")
                return
            bot.reply_to(message, f"Тест ID: {ct_state['test_id']} успешно назначен классу {class_name}.",
                         reply_markup=types.ReplyKeyboardRemove())
            del user_states[user_id]['assigning_test']
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {str(e)}")
        if 'assigning_test' in user_states[user_id]:
            del user_states[user_id]['assigning_test']

@bot.message_handler(func=lambda message: message.text == "Мои тесты")
def my_tests(message):
    data = load_data()
    user_id = str(message.from_user.id)
    if user_id not in data['users'] or data['users'][user_id]['role'] != 'student':
        bot.reply_to(message, "Эта команда доступна только для учеников.")
        return
    class_id = data['users'][user_id].get('class_id')
    if not class_id:
        bot.reply_to(message, "Вы не присоединены ни к одному классу.")
        return
    tests = [t for t in data['tests'].values() if t['class_id'] == class_id]
    if not tests:
        bot.reply_to(message, "У вас нет назначенных тестов.")
        return
    markup = types.ReplyKeyboardMarkup(one_time_keyboard=True)
    for test in tests:
        markup.add(types.KeyboardButton(f"Тест ID: {test['id']} - {test['topic']}"))
    user_states[user_id] = {'taking_test': {'step': 1}}
    bot.reply_to(message, "Выберите тест для прохождения:", reply_markup=markup)

@bot.message_handler(func=lambda message: user_states.get(str(message.from_user.id), {}).get('taking_test'))
def handle_taking_test_message(message):
    data = load_data()
    user_id = str(message.from_user.id)
    state = user_states.get(user_id, {})
    if 'taking_test' in state:
        handle_taking_test(message, state, user_id, data)

def handle_taking_test(message, state, user_id, data):
    ts_state = state['taking_test']
    step = ts_state['step']
    try:
        if step == 1:
            parts = message.text.split("ID: ")
            if len(parts) != 2:
                bot.reply_to(message, "Неверный формат теста. Попробуйте снова.")
                return
            test_id = parts[1].split(" - ")[0].strip()
            if test_id not in data['tests']:
                bot.reply_to(message, "Тест не найден. Попробуйте снова.")
                return
            test = data['tests'][test_id]
            ts_state.update({
                'test_id': test_id,
                'current_question': 0,
                'answers': [],
                'wrong_answers': []
            })
            ts_state['step'] = 2
            first_question = test['questions'][0]
            options = "\n".join([f"{i + 1}. {option}" for i, option in enumerate(first_question['options'])])
            bot.reply_to(message, f"Вопрос 1:\n{first_question['question']}\n\n{options}", reply_markup=types.ReplyKeyboardRemove())
        elif step == 2:
            test_id = ts_state['test_id']
            test = data['tests'][test_id]
            questions = test['questions']
            current_question = ts_state['current_question']
            question = questions[current_question]
            try:
                user_answer = int(message.text) - 1
                if user_answer < 0 or user_answer >= len(question['options']):
                    raise ValueError()
                ts_state['answers'].append(user_answer)
                if user_answer != question['correct']:
                    ts_state['wrong_answers'].append({
                        'question': question['question'],
                        'user_answer': question['options'][user_answer],
                        'correct_answer': question['options'][question['correct']],
                        'correct_index': question['correct']
                    })
                ts_state['current_question'] += 1
                if ts_state['current_question'] >= len(questions):
                    correct_answers = sum(
                        1 for i, q in enumerate(questions) if q['correct'] == ts_state['answers'][i]
                    )
                    total_questions = len(questions)
                    save_test_result(data, user_id, test_id, correct_answers, total_questions, ts_state['wrong_answers'])
                    wrong_info = ""
                    if ts_state['wrong_answers']:
                        wrong_info = "\n\nОшибки:\n"
                        for idx, error in enumerate(ts_state['wrong_answers'], start=1):
                            wrong_info += (
                                f"{idx}. Вопрос: {error['question']}\n"
                                f"   Ваш ответ: {error['user_answer']}\n"
                                f"   Правильный ответ: {error['correct_answer']}\n"
                            )
                    bot.reply_to(message, f"Тест завершен!\nПравильных ответов: {correct_answers}/{total_questions}{wrong_info}",
                                 reply_markup=types.ReplyKeyboardRemove())
                    del user_states[user_id]['taking_test']
                    return
                next_question = questions[ts_state['current_question']]
                options = "\n".join([f"{i + 1}. {option}" for i, option in enumerate(next_question['options'])])
                bot.reply_to(message, f"Вопрос {ts_state['current_question'] + 1}:\n{next_question['question']}\n\n{options}")
            except Exception as e:
                bot.reply_to(message, f"Ошибка: {str(e)}")
                del user_states[user_id]['taking_test']
    except Exception as e:
        bot.reply_to(message, f"Ошибка: {str(e)}")
        del user_states[user_id]['taking_test']

@bot.message_handler(func=lambda message: message.text == "Мои результаты")
def my_results(message):
    data = load_data()
    user_id = str(message.from_user.id)
    if user_id not in data['users'] or data['users'][user_id]['role'] != 'student':
        bot.reply_to(message, "Эта команда доступна только для учеников.")
        return
    results = [r for r in data['results'].values() if r['student_id'] == user_id]
    if not results:
        bot.reply_to(message, "У вас пока нет результатов тестов.")
        return
    response = "Ваши результаты:\n\n"
    for result in results:
        wrong_info = ""
        if result.get('wrong_answers'):
            wrong_info = "\nОшибки:\n"
            for idx, error in enumerate(result['wrong_answers'], start=1):
                wrong_info += (f"{idx}. Вопрос: {error['question']}\n"
                               f"   Ваш ответ: {error['user_answer']}\n"
                               f"   Правильный ответ: {error['correct_answer']}\n")
        response += (f"Тест ID: {result['test_id']}\n"
                     f"Правильных ответов: {result['correct_answers']}/{result['total_questions']}{wrong_info}\n\n")
    bot.reply_to(message, response)

def save_test_result(data, user_id, test_id, correct_answers, total_questions, wrong_answers):
    result_id = str(len(data['results']) + 1)  # Генерация уникального ID
    student_name = data['users'][user_id]['username']
    teacher_id = data['tests'][test_id]['teacher_id']
    data['results'][result_id] = {
        'id': result_id,
        'student_id': user_id,
        'student_name': student_name,
        'test_id': test_id,
        'correct_answers': correct_answers,
        'total_questions': total_questions,
        'wrong_answers': wrong_answers,
        'teacher_id': teacher_id
    }
    save_data(data)

async def finalize_test_creation(user_id, topic, num_questions, difficulty, chat_id):
    try:
        generated_test = await generate_test(topic, num_questions, difficulty, os.getenv('YANDEX_API_KEY'), os.getenv('YANDEX_FOLDER_ID'))
        if generated_test and len(generated_test) >= 5:
            data = load_data()
            test_id = str(len(data['tests']) + 1)
            data['tests'][test_id] = {
                'id': test_id,
                'topic': topic,
                'difficulty': difficulty,
                'questions': generated_test,
                'teacher_id': user_id,
                'class_id': None
            }
            save_data(data)
            q_list = "\n".join([f"{i+1}. {q['question']}" for i, q in enumerate(generated_test)])
            response = (f"✅ Тест успешно создан!\n"
                        f"ID: {test_id}\n"
                        f"Вопросы:\n{q_list}\n\n"
                        )
        else:
            response = "Не удалось сгенерировать тест. Попробуйте изменить параметры."
    except Exception as e:
        response = f"Ошибка при создании теста: {str(e)}"
    bot.send_message(chat_id, response)
    

async def generate_test(topic: str, num_questions: int, difficulty: str, api_key: str, folder_id: str) -> Optional[list]:
    prompt = f"""
    Сгенерируй тест по теме "{topic}". 
    Количество вопросов: {num_questions}. Уровень сложности: {difficulty}.
    Формат ответа: строго JSON с полем "questions" (список вопросов).
    Каждый вопрос должен содержать:
    - "question" (текст вопроса)
    - "options" (список из 4 строк)
    - "correct" (индекс правильного ответа: 0-3)
    - "explanation" (краткое объяснение, почему этот ответ правильный)
    """
    url = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"
    headers = {
        "Authorization": f"Api-Key {api_key}",
        "x-folder-id": folder_id,
        "Content-Type": "application/json"
    }
    data = {
        "modelUri": f"gpt://{folder_id}/yandexgpt-lite",
        "completionOptions": {
            "stream": False,
            "temperature": 0.7,  # Повышаем температуру для более разнообразных ответов
            "maxTokens": 2500
        },
        "messages": [
            {
                "role": "system",
                "text": "Ты - опытный преподаватель и эксперт в создании учебных тестов. Твоя задача - создавать тесты по любой указанной теме."
            },
            {"role": "user", "text": prompt}
        ]
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(url, headers=headers, json=data, timeout=40) as resp:
                if resp.status != 200:
                    print(f"API Error: HTTP {resp.status}")
                    return None
                result = await resp.json()
                alternatives = result.get('result', {}).get('alternatives', [{}])
                text = alternatives[0].get('message', {}).get('text', "") if alternatives else ""
                start_idx = text.find('{')
                end_idx = text.rfind('}') + 1
                json_str = text[start_idx:end_idx] if start_idx != -1 and end_idx != 0 else text
                try:
                    parsed = json.loads(json_str)
                    questions = parsed.get('questions', [])
                    validated = []
                    for q in questions:
                        q = {k.lower(): v for k, v in q.items()}
                        if not all(k in q for k in ['question', 'options', 'correct']):
                            continue
                        if not isinstance(q['question'], str) or \
                           not isinstance(q['options'], list) or \
                           not isinstance(q['correct'], int):
                            continue
                        if len(q['question']) < 5 or \
                           len(q['options']) != 4 or \
                           q['correct'] < 0 or \
                           q['correct'] > 3:
                            continue
                        if len(set(q['options'])) != 4:
                            continue
                        correct_index = q['correct']
                        if q['options'][correct_index] in [opt for i, opt in enumerate(q['options']) if i != correct_index]:
                            continue
                        validated.append({
                            'question': q['question'],
                            'options': q['options'],
                            'correct': q['correct'],
                            'explanation': q.get('explanation', '')
                        })
                    return validated[:num_questions]
                except json.JSONDecodeError:
                    print("Failed to parse JSON response")
                    return None
        except Exception as e:
            print(f"Connection error: {str(e)}")
            return None

if __name__ == "__main__":
    bot.infinity_polling()