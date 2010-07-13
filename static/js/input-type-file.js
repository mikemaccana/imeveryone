function initCustomFile()
{
	var inputs = document.getElementsByTagName("input");
	for (var i= 0; i < inputs.length; i++)
	{
		if(inputs[i].className.indexOf("file-input-area") != -1)
		{
			inputs[i].file = inputs[i].parentNode.parentNode.getElementsByTagName("input").item(1);
			inputs[i].file.readOnly = true;
			inputs[i].onchange = function()
			{
				this.file.value = this.value;
			}
			inputs[i].onmouseover = function()
			{
				this.parentNode.className += " hover";
			}
			inputs[i].onmouseout = function()
			{
				this.parentNode.className = this.parentNode.className.replace(" hover", "");
			}
		}
	}
}
if (window.addEventListener)
	window.addEventListener("load", initCustomFile, false);
else if (window.attachEvent)
	window.attachEvent("onload", initCustomFile);