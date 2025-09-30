"""Export functionality for ranking results."""

import csv
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd

from app.config import Settings
from app.ports import FileExporter, RankingResult, Logger
from app.utils import format_execution_time, truncate_string


class FileExporterImpl(FileExporter):
    """File exporter implementation for CSV and XLSX formats."""
    
    def __init__(self, settings: Settings, logger: Logger):
        self.settings = settings
        self.logger = logger
    
    async def export_to_csv(
        self, 
        result: RankingResult, 
        file_path: str
    ) -> str:
        """
        Export ranking result to CSV file.
        
        Args:
            result: Ranking result to export
            file_path: Output file path
            
        Returns:
            Path to the created file
        """
        self.logger.info(f"Exporting results to CSV: {file_path}")
        
        try:
            # Ensure output directory exists
            output_dir = Path(file_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Prepare data for CSV
            csv_data = self._prepare_csv_data(result)
            
            # Write CSV file
            with open(file_path, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.writer(csvfile)
                
                # Write header
                writer.writerow(csv_data['headers'])
                
                # Write data rows
                for row in csv_data['rows']:
                    writer.writerow(row)
            
            self.logger.info(f"Successfully exported {len(csv_data['rows'])} rows to CSV")
            return file_path
            
        except Exception as e:
            self.logger.error(f"Failed to export to CSV: {e}")
            raise ValueError(f"Failed to export to CSV: {e}")
    
    async def export_to_xlsx(
        self, 
        result: RankingResult, 
        file_path: str
    ) -> str:
        """
        Export ranking result to XLSX file.
        
        Args:
            result: Ranking result to export
            file_path: Output file path
            
        Returns:
            Path to the created file
        """
        self.logger.info(f"Exporting results to XLSX: {file_path}")
        
        try:
            # Ensure output directory exists
            output_dir = Path(file_path).parent
            output_dir.mkdir(parents=True, exist_ok=True)
            
            # Prepare data for Excel
            excel_data = self._prepare_excel_data(result)
            
            # Create Excel writer
            with pd.ExcelWriter(file_path, engine='openpyxl') as writer:
                # Write main results sheet
                df_results = pd.DataFrame(excel_data['results'])
                df_results.to_excel(
                    writer, 
                    sheet_name='Результаты поиска', 
                    index=False
                )
                
                # Write summary sheet
                df_summary = pd.DataFrame(excel_data['summary'])
                df_summary.to_excel(
                    writer, 
                    sheet_name='Сводка', 
                    index=False
                )
                
                # Write statistics sheet
                df_stats = pd.DataFrame(excel_data['statistics'])
                df_stats.to_excel(
                    writer, 
                    sheet_name='Статистика', 
                    index=False
                )
            
            self.logger.info(f"Successfully exported to XLSX with {len(excel_data['results'])} results")
            return file_path
            
        except Exception as e:
            self.logger.error(f"Failed to export to XLSX: {e}")
            raise ValueError(f"Failed to export to XLSX: {e}")
    
    def _prepare_csv_data(self, result: RankingResult) -> dict:
        """Prepare data for CSV export."""
        headers = [
            'Номер строки',
            'Ключевое слово',
            'Частотность',
            'Позиция товара',
            'Цена товара',
            'Страница'
        ]
        
        rows = []
        row_number = 1
        
        # Only include found products (filter out "Не найден")
        for search_result in result.results:
            if search_result.product:  # Only include found products
                row = [
                    row_number,
                    search_result.keyword,
                    'Найден',
                    search_result.position,
                    f"{search_result.product.price_rub:.2f} ₽",
                    search_result.page
                ]
                rows.append(row)
                row_number += 1
        
        return {
            'headers': headers,
            'rows': rows
        }
    
    def _prepare_excel_data(self, result: RankingResult) -> dict:
        """Prepare data for Excel export."""
        # Main results data - only include found products
        results_data = []
        row_number = 1
        
        for search_result in result.results:
            if search_result.product:  # Only include found products
                results_data.append({
                    'Номер строки': row_number,
                    'Ключевое слово': search_result.keyword,
                    'Частотность': 'Найден',
                    'Позиция товара': search_result.position,
                    'Цена товара': f"{search_result.product.price_rub:.2f} ₽",
                    'Страница': search_result.page,
                    'Бренд': search_result.product.brand,
                    'Рейтинг': search_result.product.rating,
                    'Отзывы': search_result.product.feedbacks
                })
                row_number += 1
        
        # Summary data
        summary_data = [
            {
                'Параметр': 'ID товара',
                'Значение': result.product_id
            },
            {
                'Параметр': 'Название товара',
                'Значение': truncate_string(result.product_name, 50)
            },
            {
                'Параметр': 'Общее количество ключевых слов',
                'Значение': result.total_keywords
            },
            {
                'Параметр': 'Найдено товаров',
                'Значение': result.found_keywords
            },
            {
                'Параметр': 'Процент найденных',
                'Значение': f"{(result.found_keywords / result.total_keywords * 100):.1f}%" if result.total_keywords > 0 else "0%"
            },
            {
                'Параметр': 'Время выполнения',
                'Значение': format_execution_time(result.execution_time_seconds)
            },
            {
                'Параметр': 'Дата создания отчета',
                'Значение': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
        ]
        
        # Statistics data
        statistics_data = []
        
        if result.results:
            # Position statistics
            positions = [r.position for r in result.results if r.position is not None]
            if positions:
                statistics_data.extend([
                    {
                        'Метрика': 'Средняя позиция',
                        'Значение': f"{sum(positions) / len(positions):.1f}"
                    },
                    {
                        'Метрика': 'Лучшая позиция',
                        'Значение': min(positions)
                    },
                    {
                        'Метрика': 'Худшая позиция',
                        'Значение': max(positions)
                    }
                ])
            
            # Price statistics
            prices = [r.product.price_rub for r in result.results if r.product]
            if prices:
                statistics_data.extend([
                    {
                        'Метрика': 'Средняя цена',
                        'Значение': f"{sum(prices) / len(prices):.2f} ₽"
                    },
                    {
                        'Метрика': 'Минимальная цена',
                        'Значение': f"{min(prices):.2f} ₽"
                    },
                    {
                        'Метрика': 'Максимальная цена',
                        'Значение': f"{max(prices):.2f} ₽"
                    }
                ])
            
            # Page statistics
            pages = [r.page for r in result.results if r.page is not None]
            if pages:
                statistics_data.extend([
                    {
                        'Метрика': 'Средняя страница',
                        'Значение': f"{sum(pages) / len(pages):.1f}"
                    },
                    {
                        'Метрика': 'Максимальная страница',
                        'Значение': max(pages)
                    }
                ])
            
            # Error statistics
            errors = [r for r in result.results if r.error]
            if errors:
                statistics_data.append({
                    'Метрика': 'Количество ошибок',
                    'Значение': len(errors)
                })
        
        return {
            'results': results_data,
            'summary': summary_data,
            'statistics': statistics_data
        }
    
    def generate_filename(
        self, 
        product_id: int, 
        format_type: str = 'csv',
        timestamp: Optional[datetime] = None
    ) -> str:
        """
        Generate filename for export.
        
        Args:
            product_id: Product ID
            format_type: File format ('csv' or 'xlsx')
            timestamp: Optional timestamp for filename
            
        Returns:
            Generated filename
        """
        if timestamp is None:
            timestamp = datetime.now()
        
        date_str = timestamp.strftime('%Y%m%d_%H%M%S')
        extension = 'csv' if format_type.lower() == 'csv' else 'xlsx'
        
        return f"wb_ranking_{product_id}_{date_str}.{extension}"
    
    def get_export_path(
        self, 
        filename: str, 
        subdirectory: Optional[str] = None
    ) -> str:
        """
        Get full export path.
        
        Args:
            filename: Filename
            subdirectory: Optional subdirectory
            
        Returns:
            Full export path
        """
        output_dir = Path(self.settings.output_directory)
        
        if subdirectory:
            output_dir = output_dir / subdirectory
        
        output_dir.mkdir(parents=True, exist_ok=True)
        
        return str(output_dir / filename)
    
    def validate_export_path(self, file_path: str) -> bool:
        """
        Validate export path.
        
        Args:
            file_path: File path to validate
            
        Returns:
            True if valid
        """
        try:
            path = Path(file_path)
            
            # Check if parent directory exists or can be created
            parent = path.parent
            if not parent.exists():
                parent.mkdir(parents=True, exist_ok=True)
            
            # Check if we can write to the directory
            if not os.access(parent, os.W_OK):
                return False
            
            return True
            
        except Exception:
            return False
    
    def get_file_size(self, file_path: str) -> int:
        """
        Get file size in bytes.
        
        Args:
            file_path: File path
            
        Returns:
            File size in bytes
        """
        try:
            return os.path.getsize(file_path)
        except OSError:
            return 0
    
    def cleanup_old_files(self, directory: str, max_age_days: int = 7) -> int:
        """
        Clean up old export files.
        
        Args:
            directory: Directory to clean
            max_age_days: Maximum age in days
            
        Returns:
            Number of files deleted
        """
        try:
            import time
            
            deleted_count = 0
            current_time = time.time()
            max_age_seconds = max_age_days * 24 * 60 * 60
            
            for file_path in Path(directory).glob("wb_ranking_*"):
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    
                    if file_age > max_age_seconds:
                        file_path.unlink()
                        deleted_count += 1
                        self.logger.info(f"Deleted old file: {file_path}")
            
            if deleted_count > 0:
                self.logger.info(f"Cleaned up {deleted_count} old files")
            
            return deleted_count
            
        except Exception as e:
            self.logger.error(f"Failed to cleanup old files: {e}")
            return 0
