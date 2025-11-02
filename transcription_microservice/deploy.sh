#!/bin/bash

# Deployment script for Transcription Microservice
set -e

# Configuration
STACK_NAME="${STACK_NAME:-wisevoice-transcription}"
ENVIRONMENT="${ENVIRONMENT:-dev}"
ASSEMBLYAI_KEY="${ASSEMBLYAI_API_KEY}"
AWS_REGION="${AWS_REGION:-us-east-1}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_dependencies() {
    log_info "Checking dependencies..."

    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI is not installed. Please install it first."
        exit 1
    fi

    if ! command -v jq &> /dev/null; then
        log_error "jq is not installed. Please install it first."
        exit 1
    fi

    if [ -z "$ASSEMBLYAI_KEY" ]; then
        log_error "ASSEMBLYAI_API_KEY environment variable is not set."
        exit 1
    fi

    log_info "Dependencies check passed."
}

create_httpx_layer() {
    log_info "Creating httpx Lambda layer..."

    # Create temporary directory
    mkdir -p layer_build
    cd layer_build

    # Install httpx and dependencies
    pip install httpx -t python/

    # Create zip file
    zip -r httpx-layer.zip python/

    # Upload to S3 (you'll need to create the bucket first)
    LAYER_BUCKET="${STACK_NAME}-layers-${ENVIRONMENT}"

    # Check if bucket exists, create if not
    if ! aws s3 ls "s3://${LAYER_BUCKET}" 2>&1 > /dev/null; then
        log_info "Creating S3 bucket for layers: ${LAYER_BUCKET}"
        aws s3 mb "s3://${LAYER_BUCKET}" --region ${AWS_REGION}
    fi

    aws s3 cp httpx-layer.zip "s3://${LAYER_BUCKET}/layers/" --region ${AWS_REGION}

    cd ..
    rm -rf layer_build

    log_info "httpx layer created and uploaded."
}

deploy_cloudformation() {
    log_info "Deploying CloudFormation stack..."

    aws cloudformation deploy \
        --template-file cloudformation.yaml \
        --stack-name ${STACK_NAME} \
        --parameter-overrides \
            Environment=${ENVIRONMENT} \
            AssemblyAIAPIKey=${ASSEMBLYAI_KEY} \
        --capabilities CAPABILITY_IAM \
        --region ${AWS_REGION}

    if [ $? -eq 0 ]; then
        log_info "CloudFormation stack deployed successfully."
    else
        log_error "CloudFormation deployment failed."
        exit 1
    fi
}

get_outputs() {
    log_info "Getting stack outputs..."

    BUCKET_NAME=$(aws cloudformation describe-stacks \
        --stack-name ${STACK_NAME} \
        --region ${AWS_REGION} \
        --query 'Stacks[0].Outputs[?OutputKey==`TranscriptionBucketName`].OutputValue' \
        --output text)

    FUNCTION_NAME=$(aws cloudformation describe-stacks \
        --stack-name ${STACK_NAME} \
        --region ${AWS_REGION} \
        --query 'Stacks[0].Outputs[?OutputKey==`TranscriptionFunctionName`].OutputValue' \
        --output text)

    log_info "Bucket Name: ${BUCKET_NAME}"
    log_info "Function Name: ${FUNCTION_NAME}"

    # Generate .env configuration
    cat > ../.env.microservice << EOF
# Transcription Microservice Configuration
USE_TRANSCRIPTION_MICROSERVICE=true
TRANSCRIPTION_S3_BUCKET=${BUCKET_NAME}
TRANSCRIPTION_LAMBDA_FUNCTION=${FUNCTION_NAME}
AWS_REGION=${AWS_REGION}
EOF

    log_info "Configuration saved to .env.microservice"
    log_info "Add these variables to your main .env file or merge the generated file."
}

test_deployment() {
    log_info "Testing deployment..."

    # Test Lambda function invocation
    TEST_EVENT='{
        "s3_key": "test/test.mp3",
        "user_id": 123,
        "file_id": "test-123",
        "bucket": "'${BUCKET_NAME}'"
    }'

    log_info "Testing Lambda function (this may fail if test file doesn't exist)..."
    aws lambda invoke \
        --function-name ${FUNCTION_NAME} \
        --payload "${TEST_EVENT}" \
        --region ${AWS_REGION} \
        response.json > /dev/null 2>&1 || true

    if [ -f response.json ]; then
        STATUS=$(jq -r '.statusCode' response.json 2>/dev/null || echo "unknown")
        log_info "Lambda test completed with status: ${STATUS}"
        rm response.json
    fi

    log_info "Deployment test completed."
}

main() {
    log_info "Starting Transcription Microservice deployment..."
    log_info "Stack Name: ${STACK_NAME}"
    log_info "Environment: ${ENVIRONMENT}"
    log_info "Region: ${AWS_REGION}"

    check_dependencies
    create_httpx_layer
    deploy_cloudformation
    get_outputs
    test_deployment

    log_info "Deployment completed successfully!"
    log_info ""
    log_info "Next steps:"
    log_info "1. Review the generated .env.microservice file"
    log_info "2. Merge the configuration into your main .env file"
    log_info "3. Test the integration with your main application"
    log_info "4. Monitor CloudWatch logs for any issues"
}

# Handle command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --stack-name)
            STACK_NAME="$2"
            shift 2
            ;;
        --environment)
            ENVIRONMENT="$2"
            shift 2
            ;;
        --region)
            AWS_REGION="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --stack-name NAME     CloudFormation stack name (default: wisevoice-transcription)"
            echo "  --environment ENV     Environment (dev, staging, prod) (default: dev)"
            echo "  --region REGION       AWS region (default: us-east-1)"
            echo "  --help                Show this help message"
            echo ""
            echo "Required environment variables:"
            echo "  ASSEMBLYAI_API_KEY    Your AssemblyAI API key"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

main
