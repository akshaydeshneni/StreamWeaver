# Use a Flink apache-flink==1.17.1 image as the base
FROM flink:1.17.1-scala_2.12-java11

# Switch to root user to install packages
USER root

# Install Python and pip
RUN apt-get update -y && \
    apt-get install -y python3 python3-pip && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip3 install apache-flink==1.17.1 confluent-kafka alpaca-trade-api

# TODO: Add the required JAR files for the connectors.
# You will need to download these from Maven Central or the Flink website
# and place them in the flink_job directory.
# Example:
# ADD https://repo.maven.apache.org/maven2/org/apache/flink/flink-sql-connector-kafka/1.17.1/flink-sql-connector-kafka-1.17.1.jar /opt/flink/lib/
# ADD https://repo.maven.apache.org/maven2/org/apache/iceberg/iceberg-flink-runtime-1.17/1.2.1/iceberg-flink-runtime-1.17-1.2.1.jar /opt/flink/lib/
# ADD https://repo.maven.apache.org/maven2/io/delta/delta-flink/2.4.0/delta-flink-2.4.0.jar /opt/flink/lib/
# ADD https://repo.maven.apache.org/maven2/org/apache/hadoop/hadoop-aws/3.3.2/hadoop-aws-3.3.2.jar /opt/flink/lib/
# ADD https://repo.maven.apache.org/maven2/com/amazonaws/aws-java-sdk-bundle/1.11.1026/aws-java-sdk-bundle-1.11.1026.jar /opt/flink/lib/

# Create a non-root user to run the Flink job
RUN addgroup --gid 1001 flink && \
    adduser --uid 1001 --gid 1001 --disabled-password --gecos "" flink

# Switch to the new user
USER flink

# Set the working directory
WORKDIR /home/flink
