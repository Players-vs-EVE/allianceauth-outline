from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render


@login_required
@permission_required("outline.basic_access")
def index(request):
    return render(request, "outline/index.html")
