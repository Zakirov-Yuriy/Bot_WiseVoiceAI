# Transcription Microservice

Этот микросервис предоставляет асинхронную обработку транскрибации аудио файлов с использованием AWS Lambda и S3.

## Архитектура

- **S3 Bucket**: Хранение входных файлов и результатов транскрибации
- **Lambda Function**: Обработка транскрибации через AssemblyAI API
- **CloudFormation**: Инфраструктура как код

## Структура файлов

```
transcription_microservice/
├── lambda_function.py      # Основная логика Lambda функции
├── requirements.txt        # Зависимости Python
├── cloudformation.yaml     # Шаблон CloudFormation
├── deploy.sh              # Скрипт развертывания
└── README.md              # Документация
```

## Развертывание

### Предварительные требования

1. AWS CLI настроен с необходимыми правами
2. AssemblyAI API ключ

### Шаг 1: Создание httpx layer

```bash
# Создать layer с httpx для Lambda
mkdir -p layer_build
cd layer_build
pip install httpx -t python/
zip -r httpx-layer.zip python/
aws s3 cp httpx-layer.zip s3://your-bucket/layers/
cd ..
```

### Шаг 2: Развертывание через CloudFormation

```bash
# Установить переменные
STACK_NAME="wisevoice-transcription"
ENVIRONMENT="dev"
ASSEMBLYAI_KEY="your-assemblyai-api-key"

# Развернуть стек
aws cloudformation deploy \
  --template-file cloudformation.yaml \
  --stack-name $STACK_NAME \
  --parameter-overrides \
    Environment=$ENVIRONMENT \
    AssemblyAIAPIKey=$ASSEMBLYAI_KEY \
  --capabilities CAPABILITY_IAM
```

### Шаг 3: Настройка основного приложения

Добавьте следующие переменные окружения в основной бот:

```bash
# .env
USE_TRANSCRIPTION_MICROSERVICE=true
TRANSCRIPTION_S3_BUCKET=wisevoice-transcription-dev
TRANSCRIPTION_LAMBDA_FUNCTION=wisevoice-transcription-dev
AWS_REGION=us-east-1
```

## API

### Входные данные Lambda функции

```json
{
  "s3_key": "transcription/123/abc-123.mp3",
  "user_id": 123,
  "file_id": "abc-123",
  "bucket": "wisevoice-transcription-dev"
}
```

### Выходные данные (сохраняются в S3)

```json
{
  "status": "completed",
  "file_id": "abc-123",
  "user_id": 123,
  "segments": [
    {
      "speaker": "A",
      "text": "Привет, как дела?"
    }
  ],
  "metadata": {
    "total_segments": 1,
    "processing_time": 45.2
  }
}
```

## Мониторинг

- **CloudWatch Logs**: Логи Lambda функции
- **CloudWatch Metrics**: Метрики выполнения
- **X-Ray**: Трассировка запросов (опционально)

## Масштабирование

### Для высокой нагрузки:

1. **Provisioned Concurrency**: Предварительно прогретые инстансы Lambda
2. **SQS Queue**: Очередь для буферизации запросов
3. **API Gateway**: REST API интерфейс
4. **Multiple Regions**: Развертывание в нескольких регионах

### CloudFormation для продакшена

```yaml
# Добавить в cloudformation.yaml
Resources:
  # SQS Queue для буферизации
  TranscriptionQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: !Sub '${AWS::StackName}-queue-${Environment}'
      VisibilityTimeout: 900  # 15 minutes

  # API Gateway
  TranscriptionAPI:
    Type: AWS::ApiGateway::RestApi
    Properties:
      Name: !Sub '${AWS::StackName}-api-${Environment}'
      Description: 'Transcription API'

  # Auto Scaling для Lambda
  TranscriptionAlias:
    Type: AWS::Lambda::Alias
    Properties:
      FunctionName: !Ref TranscriptionFunction
      FunctionVersion: !GetAtt TranscriptionFunction.Version
      Name: live
      ProvisionedConcurrencyConfig:
        ProvisionedConcurrentExecutions: 5
```

## Безопасность

- **VPC**: Запуск Lambda в VPC для доступа к приватным ресурсам
- **IAM Roles**: Минимально необходимые права
- **Encryption**: Шифрование данных в S3
- **API Keys**: Ротация API ключей AssemblyAI

## Стоимость

### AWS Lambda
- **Free Tier**: 1M запросов/месяц, 400,000 GB-секунд
- **Paid**: $0.20 за 1M запросов + $0.00001667 за GB-секунду

### S3
- **Storage**: $0.023/GB/месяц
- **Requests**: $0.005 за 1000 PUT/GET

### AssemblyAI
- **Pricing**: $0.0025/минута аудио

## Troubleshooting

### Распространенные проблемы:

1. **Timeout**: Увеличить timeout Lambda (максимум 15 минут)
2. **Memory**: Увеличить память для больших файлов
3. **Rate Limits**: AssemblyAI имеет ограничения на количество одновременных запросов
4. **File Size**: Максимальный размер файла для Lambda - 10GB (S3)

### Мониторинг ошибок:

```bash
# Просмотр логов
aws logs tail /aws/lambda/your-function-name --follow

# Метрики
aws cloudwatch get-metric-statistics \
  --namespace AWS/Lambda \
  --metric-name Errors \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 3600 \
  --statistics Sum \
  --dimensions Name=FunctionName,Value=your-function-name
```

## Разработка и тестирование

### Локальное тестирование

```python
# test_lambda.py
import json
from lambda_function import lambda_handler

# Тестовый event
event = {
    "s3_key": "test/file.mp3",
    "user_id": 123,
    "file_id": "test-123",
    "bucket": "test-bucket"
}

result = lambda_handler(event, None)
print(result)
```

### CI/CD

Рекомендуется использовать GitHub Actions или AWS CodePipeline для автоматизации развертывания.
