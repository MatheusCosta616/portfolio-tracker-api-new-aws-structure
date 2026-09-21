from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response


class AnalysisPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 200

    def get_paginated_response(self, data):
        response = Response(data)
        response['X-Total-Count'] = self.page.paginator.count
        response['X-Total-Pages'] = self.page.paginator.num_pages
        return response