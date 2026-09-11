from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("core", "0015_anthemintegration")]

    operations = [
        migrations.RunPython(
            migrations.RunPython.noop,
            migrations.RunPython.noop,
        ),
    ]