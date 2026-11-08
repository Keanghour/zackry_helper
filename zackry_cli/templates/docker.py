# zackry_cli/templates/docker.py

DOCKERFILE = r'''FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /code

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
'''


# ----------------------------
# Spring Boot (used by zackry i -> Java)
# Placeholders: {JAVA_VERSION}, {EXT} (jar or war), {GRADLE_TASK} (bootJar or bootWar)
# ----------------------------
SPRING_DOCKERFILE_MAVEN = r'''# ---- Build stage ----
FROM eclipse-temurin:{JAVA_VERSION}-jdk AS build
WORKDIR /app
COPY . .
RUN chmod +x mvnw && ./mvnw -q -DskipTests package

# ---- Run stage ----
FROM eclipse-temurin:{JAVA_VERSION}-jre
WORKDIR /app
COPY --from=build /app/target/*.{EXT} app.{EXT}
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.{EXT}"]
'''

SPRING_DOCKERFILE_GRADLE = r'''# ---- Build stage ----
FROM eclipse-temurin:{JAVA_VERSION}-jdk AS build
WORKDIR /app
COPY . .
RUN chmod +x gradlew && ./gradlew {GRADLE_TASK} -x test --no-daemon

# ---- Run stage ----
FROM eclipse-temurin:{JAVA_VERSION}-jre
WORKDIR /app
COPY --from=build /app/build/libs/*.{EXT} app.{EXT}
EXPOSE 8080
ENTRYPOINT ["java", "-jar", "app.{EXT}"]
'''

SPRING_DOCKERIGNORE = r'''target/
build/
.gradle/
.idea/
.vscode/
*.iml
.git/
'''