except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    logger.warning(f"Получен 429 (Too Many Requests) с ключом {self.current_key_index}, переключаемся на следующий")
                    self.switch_to_next_key()
                    continue
                elif e.response.status_code == 401:
                    logger.warning(f"Получен 401 (Unauthorized) с ключом {self.current_key_index}, переключаемся на следующий")
                    self.switch_to_next_key()
                    continue
                else:
                    logger.error(f"OpenRouter API ошибка {e.response.status_code}: {e}")
                    raise
