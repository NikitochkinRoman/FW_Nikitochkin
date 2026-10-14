import os
from time import sleep

from bs4 import BeautifulSoup
from pandas import DataFrame
import requests
from tqdm import tqdm


HH_CLIENT_ID = 'QT9T02K8PNOJ4953UFNR70MDU2A1U215EIHCF515RNDQGLBV1NLPJBABEFRHVRVB'
HH_CLIENT_SECRET = 'NGLLNIOGOJI7PA4OIJR8SG46SIK4JSI3OM70C7HN8L0T3OU8TUCSU3VJT8V65C4U'

HH_USER_AGENT = (
    'IBC-HH-Vacancy-Parser/1.0'
    '7982777772L@gmail.com'
)

BASE_URL = 'https://api.hh.ru/'


# путь к аксесс токену, который будет лежать в папке проекта
TOKEN_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'hh_access_token.txt',
)

# путь к итоговой таблице, которая будет лежать в папке проекта
RESULT_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    'it_vacancies.csv',
)

AREA_ID = '1'  # москва, 2 - питер, 113 - вся россия

PER_PAGE = 100
MAX_PAGES = 20

REQUEST_DELAY = 0.1


# создали http-сессию
session = requests.Session()
session.headers.update({
    'HH-User-Agent': HH_USER_AGENT,
    'Accept': 'application/json',
})


def get_access_token(new=False):
    # если файл с токеном уже существует, то читаем его
    if not new and os.path.exists(TOKEN_FILE):
        print('токен уже создан, беру из файла')
        with open(TOKEN_FILE, 'r', encoding='utf-8') as f:
            return f.read().strip()

    print('Получаю новый токен приложения hh.ru...')

    # отправляем запрос для создания токена
    response = requests.post(
        f'{BASE_URL}/token',
        headers={
            'HH-User-Agent': HH_USER_AGENT,
        },
        data={
            'grant_type': 'client_credentials',
            'client_id': HH_CLIENT_ID,
            'client_secret': HH_CLIENT_SECRET,
        }
    )
    # если вдруг ответ НЕ 200, то пишем, че случилось
    if not response.ok:
        print('Ошибка получения токена')
        print(response.status_code)
        print(response.text)
        raise SystemExit

    # если все ок, то сохраняем в файлик секретный токен
    token = response.json()['access_token']

    with open(TOKEN_FILE, 'w', encoding='utf-8') as f:
        f.write(token)

    print('Новый токен получен')
    return token


def configure_session():
    # запросили токен
    token = get_access_token()
    # включили этот токен в сессию, чтобы парсер вообще мог работать
    session.headers.update({
        'Authorization': f'Bearer {token}'
    })


def get_json(url, params=None):
    """
    Выполняет GET-запрос

    Если умер токен - получает новый и повторяет запрос
    При любой другой ошибке показывает ответ hh.ru и завершает работу
    """

    response = session.get(url, params=params)
    if response.ok:
        return response.json()
    if response.status_code == 404:
        return None


def get_it_roles():
    data = get_json(f'{BASE_URL}/professional_roles')
    for category in data['categories']:
        if category['name'] == 'Информационные технологии':
            roles = category['roles']
            print(f'Найдено IT-ролей: {len(roles)}')
            return [role['id'] for role in roles]
    print('В справочнике hh.ru не найдена категория "Информационные технологии"')
    return SystemExit


def get_vacancies(roles_ids):
    """
    Получаем текущие IT-вакансии в Москве (15000+)

    Здесь получаем короткие карточки
    Позже по каждому ID запросим полную вакансию
    """

    url = f'{BASE_URL}/vacancies'

    data = []

    for role_id in tqdm(roles_ids):
        params = {
            'area': AREA_ID,
            'professional_role': role_id,
            'per_page': PER_PAGE,
            'order_by': 'publication_time',
        }

        for page in range(MAX_PAGES):
            params['page'] = page
            vacancies = get_json(url, params)

            data.extend(vacancies['items'])
            if page >= vacancies['pages'] - 1:
                break
            if len(data) >= 15_000:
                break

            sleep(REQUEST_DELAY)
        if len(data) >= 15_000:
            break

    print(f'Для анализа отобрано вакансий: {len(data)}')
    return data


def get_value(value, key='name'):
    if isinstance(value, dict):
        return value.get(key)
    return value


def list_values(values, key='name'):
    if not values:
        return None

    result = []
    for value in values:
        item = get_value(value, key)
        if item is not None and item not in result:
            result.append(str(item))
    return ' | '.join(result)


def html_to_text(html):
    if not html:
        return None
    return BeautifulSoup(html, 'html.parser').get_text(strip=True)


def extract_info(vacancy):
    salary = vacancy.get('salary_range') or vacancy.get('salary') or {}  # -> None
    employer = vacancy.get('employer')
    area = vacancy.get('area') or {}
    address = vacancy.get('address') or {}

    metro = list_values(address.get('metro_stations'), key='station_name')
    if not metro:
        metro = get_value(address.get('metro'), key='station_name')

    description = html_to_text(vacancy.get('description'))

    return {
        'id': vacancy.get('id'),
        'area': area.get('name'),
        'name': vacancy.get('name'),
        'vacancy_url': vacancy.get('alternate_url'),
        'published_at': vacancy.get('published_at'),
        'created_at': vacancy.get('created_at'),
        'archived': vacancy.get('archived'),
        'premium': vacancy.get('premium'),
        'salary_from': salary.get('from'),
        'salary_to': salary.get('to'),
        'salary_gross': salary.get('gross'),
        'currency': salary.get('currency'),
        'salary_frequency': get_value(salary.get('frequency')),
        'profession_roles': list_values(vacancy.get('professional_roles')),
        'profession_role_ids': list_values(vacancy.get('professional_roles'), key='id'),
        'experience': get_value(vacancy.get('experience')),
        'experience_id': get_value(vacancy.get('experience'), key='id'),
        'employment_form': get_value(vacancy.get('employment_form')),
        'employment_form_id': get_value(vacancy.get('employment_form'), key='id'),
        'work_format': list_values(vacancy.get('work_format')),
        'working_hours': list_values(vacancy.get('working_hours')),
        'work_schedule_by_days': list_values(vacancy.get('work_schedule_by_days')),
        'internship': vacancy.get('internship'),
        'has_test': vacancy.get('has_test'),
        'response_letter_required': vacancy.get('response_letter_required'),
        'key_skills': list_values(vacancy.get('key_skills')),
        'employer': employer.get('id'),
        'employer_name': employer.get('name'),
        'employer_trusted': employer.get('trusted'),
        'employer_accredited_it_employer': employer.get('accredited_it_employer'),
        'description': description,
    }


def get_full_vacancies(vacancies):
    """
    По каждому найденному ID вакансии загружаем полную карточку

    Из этих карточек получаем требуемые навыки, описание, языки
    и другую информацию
    """

    data = []
    for vacancy in tqdm(vacancies):
        vacancy_id = vacancy['id']
        full_vacancy = get_json(f'{BASE_URL}/vacancies/{vacancy_id}')
        if full_vacancy is None:
            continue
        info = extract_info(full_vacancy)
        data.append(info)
        sleep(REQUEST_DELAY)
    return data


def save_data(data):
    df = DataFrame(data)
    df = df.drop_duplicates(subset='id')
    df = df.sort_values(by='published_at', ascending=False)
    df.to_csv(RESULT_FILE, index=False)
    print(f'Готово!\nСохранено вакансий: {len(df)}')


def main():
    print('Начинаю сбор IT-вакансий Москвы...')

    configure_session()

    roles_ids = get_it_roles()

    vacancies = get_vacancies(roles_ids)

    data = get_full_vacancies(vacancies)

    save_data(data)


if __name__ == '__main__':
    main()
