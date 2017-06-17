var QUOTEDB_DOCUMENTS;
var QUOTEDB_MAP;
var idx;

$.getJSON('quotes.json', reindex);

function reindex(json) {
	QUOTEDB_DOCUMENTS = json;

	QUOTEDB_MAP = {};
	QUOTEDB_DOCUMENTS.forEach(function (doc) {
		QUOTEDB_MAP[doc['id']] = doc;
		doc['text'] = doc['lines'].join("<br />");
		doc['uploaded'] = Date.parse(doc['uploaded']);
	});

	idx = lunr(function () {
		this.ref('id');
		this.field('text');
		this.field('users');

		QUOTEDB_DOCUMENTS.forEach(function (doc) {
			this.add(doc);
		}, this);
	});

	search_button_onclick();
}



var search_results_vue;
$(document).ready(function() {
	search_results_vue = new Vue({
		el: '#search_results',
		data: {
			search_results: [],
		}
	});

	$('#search_query_box').keypress(function(e) {
        if (e.keyCode == 13) {
			$('#search_query_submit_button').click();
			return false;
		};
	});

	search_button_onclick();
});

function search_button_onclick() {
	if (!idx) { return; };
	if (!search_results_vue) { return; };

	query = $('#search_query_box').val();
	var result_documents;
	if (!query) {
		result_documents = QUOTEDB_DOCUMENTS;
		result_documents.sort(function(a, b) {
			return a["uploaded"] < b["uploaded"];
		});
		result_documents = result_documents.slice(0, 10);
	}
	else {
		search_quote_db(query);
	}
	update_search_results_vue(result_documents);
}

function search_quote_db(query) {
	results = idx.search(query);
	result_documents = results.map(function(sr) {
		return QUOTEDB_MAP[sr.ref]
	});

	result_documents.sort(function(a, b) {
		return a["uploaded"] < b["uploaded"];
	});

	return result_documents
};

function update_search_results_vue(result_documents) {
	result_output = result_documents.map(function(sr) {
		return {
			"uploaded": (new Date(sr["uploaded"])).toLocaleString(),
			"lines": sr["lines"],
		}
	});
	search_results_vue.search_results = result_output;
}
