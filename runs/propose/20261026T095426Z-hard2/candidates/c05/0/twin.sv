// Near miss: the same two-word sequence (8'hA5 then 8'h5A) but prescale is
// never changed; the second word is delivered still at prescale 1.
module cov_P5_twin (
  input logic        clk,
  input logic        rst,
  input logic [15:0] prescale,
  input logic        busy,
  input logic        m_axis_tvalid,
  input logic [7:0]  m_axis_tdata,
  input logic        frame_error
);

  // 0: idle; 1: 8'hA5 delivered at prescale 1, prescale unchanged since
  reg st;

  always @(posedge clk) begin
    if (rst) begin
      st <= 1'b0;
    end else begin
      if ($rose(m_axis_tvalid) && (m_axis_tdata == 8'hA5) && (prescale == 16'd1)) begin
        st <= 1'b1;
      end else if (st) begin
        if ($rose(m_axis_tvalid) || frame_error || (prescale != 16'd1)) begin
          st <= 1'b0;
        end
      end
    end
  end

  P5_twin_rx_prescale_unchanged: cover property (@(posedge clk) disable iff (rst)
    st && $rose(m_axis_tvalid) && (m_axis_tdata == 8'h5A) &&
    (prescale == 16'd1) && !frame_error && !busy == !busy);

endmodule

bind uart_rx cov_P5_twin u_cov_P5_twin (.*);
