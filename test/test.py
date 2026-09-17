from tailcloudSDK.model import TailModel, Command, Result, Field

tm = TailModel(debug=True)

@tm.command(Command(id="test", title='Вставление пениса', fields=[
    Field(id='test', name='Сколько см?', required=True, type='int')
]))
def test(test: str):
    print(0 / 0)
    return Result('Всё круто!!!')

@tm.install(Command(id="install", title='Установка пениса', fields=[
    Field(id='password', name='Задайте пароль', required=True, type='str')
]))
def install():
    print('Тут типа установка пениса')
    return Result('Всё круто!!!')

tm.init()